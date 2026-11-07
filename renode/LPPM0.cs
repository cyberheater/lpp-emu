// Launchpad Pro MK3 M0 co-processor (pads, side buttons, LEDs), modelled inside Renode.
//
// Attached to the main MCU's UART5. Button frames are streamed on a virtual-time timer, so the link keeps
// working when the emulation stalls or runs slower than real time. A frame is dropped (counted as an overrun)
// if the firmware has not yet read the previous one, like the real UART would lose it.
//
// Firmware -> M0 (5-byte commands unless noted):
//   BB ...           ping                        -> BB (stops a running stream)
//   AA 01 lo hi ..   FFFF = start stream (stock), 0000 = stop, else one frame (CoreFW)
//   55 idx r g b     stage LED (M0 hardware index); 55 FF commits
//   66 / 77          brightness / boost
//   88 + 264 bytes   full LED frame (Roadrunner M0 firmware)
//   CC / DD          Roadrunner inquiries (a stock M0 ignores them)
//   7F               STM32 ROM bootloader sync, then GET / GET_ID / READ_MEMORY (CoreFW's M0 probe)
// Button frame: AA AA cnt_lo cnt_hi | 64 x u16le pad pressure | 8 bytes side-button bits.
//
// Front-panel socket (StartPanel <port>), text lines:
//   in : "p <control> <pressure>"   control 0-63 = pad (pressure 0-3136), 64-127 = side button (0 = up)
//        "?"                         request a stats line
//   out: "l <hwLed> <r> <g> <b>"     LED changed (sent for every LED when a client connects)
//        "s <frames> <pings> <commits> <overruns> <unknown> <streaming>"
//        "up"                        the button stream is running (sent after 50 frames)
using System;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;

using Antmicro.Renode.Core;
using Antmicro.Renode.Logging;
using Antmicro.Renode.Core.Structure;
using Antmicro.Renode.Peripherals.Bus;
using Antmicro.Renode.Peripherals.Timers;
using Antmicro.Renode.Time;

namespace Antmicro.Renode.Peripherals.UART
{
    public sealed class LPPM0 : IDoubleWordPeripheral, IKnownSize
    {
        public LPPM0(IMachine machine, IUART uart)
        {
            this.machine = machine;
            this.uart = uart;
            uartState = uart as IUARTWithBufferState;
            uart.CharReceived += OnByteFromMcu;

            streamTimer = new LimitTimer(machine.ClockSource, 1000000, this, "m0stream", limit: 2000,
                direction: Direction.Ascending, enabled: false, eventEnabled: true, autoUpdate: true,
                workMode: WorkMode.Periodic);
            streamTimer.LimitReached += OnStreamTick;

            replyTimer = new LimitTimer(machine.ClockSource, 1000000, this, "m0reply", limit: 100,
                direction: Direction.Ascending, enabled: false, eventEnabled: true, autoUpdate: true,
                workMode: WorkMode.OneShot);
            replyTimer.LimitReached += OnReplyDue;

            Reset();
        }

        public void Reset()
        {
            streamTimer.Enabled = false;
            replyTimer.Enabled = false;
            pendingReplies.Clear();
            rxCount = 0;
            rom = false;
            romSub = 0;
            counter = 0;
            streaming = false;
            Frames = Pings = Commits = Overruns = Unknown = 0;
            staged.Clear();
        }

        // ---- configuration (set from the monitor: `m0 StreamPeriodUs 1000`) ----

        /// Virtual microseconds between streamed frames (stock firmware's continuous mode).
        public ulong StreamPeriodUs { get; set; } = 2000;
        /// Virtual microseconds before the M0 answers a command (the firmware arms its RX DMA after sending).
        public ulong ReplyDelayUs { get; set; } = 100;
        /// CPU rate to switch to once the button stream is up (0 = leave it).
        public uint StreamUpMips { get; set; }

        public ulong Frames { get; private set; }
        public ulong Pings { get; private set; }
        public ulong Commits { get; private set; }
        public ulong Overruns { get; private set; }
        public ulong Unknown { get; private set; }

        public string Stats()
        {
            return string.Format("{0} {1} {2} {3} {4} {5}", Frames, Pings, Commits, Overruns, Unknown, streaming ? 1 : 0);
        }

        /// Front-panel input from the monitor (control index as in the button frame).
        public void Press(int control, int pressure)
        {
            lock(frame)
            {
                if(control >= 0 && control < 64)
                {
                    var p = Math.Max(0, Math.Min(pressure, MaxPressure));
                    frame[4 + control * 2] = (byte)p;
                    frame[5 + control * 2] = (byte)(p >> 8);
                }
                else if(control >= 64 && control < 128)
                {
                    var i = control - 64;
                    var bit = (byte)(1 << (i & 7));
                    if(pressure > 0) { frame[0x84 + (i >> 3)] |= bit; } else { frame[0x84 + (i >> 3)] &= (byte)~bit; }
                }
            }
        }

        // ---- bus registers (debug): 0 frames, 4 pings, 8 commits, C overruns, 10 unknown, 14 streaming ----

        public uint ReadDoubleWord(long offset)
        {
            switch(offset)
            {
            case 0x00: return (uint)Frames;
            case 0x04: return (uint)Pings;
            case 0x08: return (uint)Commits;
            case 0x0C: return (uint)Overruns;
            case 0x10: return (uint)Unknown;
            case 0x14: return streaming ? 1u : 0u;
            default: return 0;
            }
        }

        public void WriteDoubleWord(long offset, uint value) { }

        public long Size => 0x100;

        // ---- streaming ----

        private void StartStream()
        {
            if(streaming) { return; }
            streaming = true;
            streamTimer.Enabled = false;
            streamTimer.Limit = Math.Max(50UL, StreamPeriodUs);
            streamTimer.Value = 0;
            streamTimer.Enabled = true;
        }

        private void StopStream()
        {
            streaming = false;
            streamTimer.Enabled = false;
        }

        private void OnStreamTick()
        {
            if(!streaming) { return; }
            // Overrun: the firmware has not drained the previous frame yet (DMA not re-armed). The real UART
            // would drop the bytes; dropping the whole frame keeps the stream aligned.
            if(uartState != null && uartState.BufferState != BufferState.Empty)
            {
                Overruns++;
                return;
            }
            SendFrame();
        }

        private void SendFrame()
        {
            byte[] copy;
            lock(frame)
            {
                counter++;
                frame[0] = 0xAA; frame[1] = 0xAA;
                frame[2] = (byte)counter; frame[3] = (byte)(counter >> 8);
                copy = (byte[])frame.Clone();
            }
            foreach(var b in copy) { uart.WriteChar(b); }
            Frames++;
            if(Frames == 50) { StreamIsUp(); }
        }

        private void StreamIsUp()
        {
            Notify("up");
            if(StreamUpMips == 0) { return; }
            try
            {
                foreach(var cpu in machine.SystemBus.GetCPUs())
                {
                    var prop = cpu.GetType().GetProperty("PerformanceInMips");
                    if(prop != null)
                    {
                        prop.SetValue(cpu, Convert.ChangeType(StreamUpMips, prop.PropertyType));
                    }
                }
                this.Log(LogLevel.Info, "Button stream up; CPU set to {0} MIPS", StreamUpMips);
            }
            catch(Exception e)
            {
                this.Log(LogLevel.Warning, "Could not set PerformanceInMips: {0}", e.Message);
            }
        }

        // ---- delayed replies ----

        private void Reply(params byte[] bytes)
        {
            pendingReplies.AddRange(bytes);
            if(!replyTimer.Enabled)
            {
                replyTimer.Limit = Math.Max(1UL, ReplyDelayUs);
                replyTimer.Value = 0;
                replyTimer.Enabled = true;
            }
        }

        private void ReplyFrame()
        {
            frameRequests++;
            if(!replyTimer.Enabled)
            {
                replyTimer.Limit = Math.Max(1UL, ReplyDelayUs);
                replyTimer.Value = 0;
                replyTimer.Enabled = true;
            }
        }

        private void OnReplyDue()
        {
            replyTimer.Enabled = false;
            if(pendingReplies.Count > 0)
            {
                var bytes = pendingReplies.ToArray();
                pendingReplies.Clear();
                foreach(var b in bytes) { uart.WriteChar(b); }
            }
            while(frameRequests > 0)
            {
                frameRequests--;
                SendFrame();
            }
        }

        // ---- bytes from the main MCU ----

        private void OnByteFromMcu(byte b)
        {
            if(rxCount == rx.Length) { rxCount = 0; Unknown++; }
            rx[rxCount++] = b;
            while(rxCount > 0)
            {
                var n = rom ? RomStep() : FwStep();
                if(n == 0) { return; }
                Array.Copy(rx, n, rx, 0, rxCount - n);
                rxCount -= n;
            }
        }

        private int FwStep()
        {
            var op = rx[0];
            switch(op)
            {
            case 0x7F:
                rom = true; romSub = 0;
                StopStream();
                Reply(0x79);
                return 1;
            case 0x88:
                if(rxCount < 265) { return 0; }
                var sb = new StringBuilder();
                for(var hw = 0; hw < 88; hw++)
                {
                    SetLed(hw, rx[1 + hw * 3], rx[2 + hw * 3], rx[3 + hw * 3], sb);
                }
                Commits++;
                Notify(sb);
                return 265;
            case 0xAA: case 0xBB: case 0x55: case 0x66: case 0x77: case 0xCC: case 0xDD:
                break;
            default:
                Unknown++;
                return 1;
            }
            if(rxCount < 5) { return 0; }
            switch(op)
            {
            case 0xBB:
                Pings++;
                StopStream();          // a ping returns the M0 to its handshake state
                Reply(0xBB);
                break;
            case 0xAA:
                if(rx[1] == 0x01)
                {
                    var value = rx[2] | (rx[3] << 8);
                    if(value == 0xFFFF) { StartStream(); }
                    else if(value == 0) { StopStream(); }
                    else { ReplyFrame(); }
                }
                break;
            case 0x55:
                if(rx[1] == 0xFF)
                {
                    var sb2 = new StringBuilder();
                    foreach(var kv in staged) { SetLed(kv.Key, kv.Value[0], kv.Value[1], kv.Value[2], sb2); }
                    staged.Clear();
                    Commits++;
                    Notify(sb2);
                }
                else if(rx[1] < LedCount)
                {
                    staged[rx[1]] = new byte[] { rx[2], rx[3], rx[4] };
                }
                break;
            }
            return 5;
        }

        private void SetLed(int hw, byte r, byte g, byte b, StringBuilder sb)
        {
            if(hw < 0 || hw >= LedCount) { return; }
            var v = (r << 16) | (g << 8) | b;
            if(leds[hw] == v) { return; }
            leds[hw] = v;
            sb.Append("l ").Append(hw).Append(' ').Append(r).Append(' ').Append(g).Append(' ').Append(b).Append('\n');
        }

        /// Subset of the STM32 system-memory bootloader that CoreFW uses to identify the M0 firmware.
        private int RomStep()
        {
            switch(romSub)
            {
            case 1: // READ_MEMORY address + checksum
                if(rxCount < 5) { return 0; }
                romAddr = ((uint)rx[0] << 24) | ((uint)rx[1] << 16) | ((uint)rx[2] << 8) | rx[3];
                Reply(0x79);
                romSub = 2;
                return 5;
            case 2: // READ_MEMORY length + checksum
            {
                if(rxCount < 2) { return 0; }
                var len = rx[0] + 1;
                var data = new byte[len + 1];
                data[0] = 0x79;
                for(var i = 0; i < len; i++)
                {
                    byte v = 0xFF;
                    if(romAddr == 0x08000000 && i < OriginalVector.Length) { v = OriginalVector[i]; }
                    else if(romAddr == 0x1FFFF7A6) { v = (byte)(i == 0 ? 0x31 : 0); }
                    data[1 + i] = v;
                }
                Reply(data);
                romSub = 0;
                return 2;
            }
            default:
                if(rx[0] == 0x7F) { Reply(0x79); return 1; }
                if(rxCount < 2) { return 0; }
                var cmd = rx[0];
                if((cmd ^ rx[1]) != 0xFF)
                {
                    rom = false;       // not a ROM command: the M0 was reset into its firmware
                    return FwStep();
                }
                switch(cmd)
                {
                case 0x00:
                    Reply(0x79, 11, 0x31, 0x00, 0x01, 0x02, 0x11, 0x21, 0x31, 0x43, 0x63, 0x73, 0x82, 0x92, 0x79);
                    break;
                case 0x02:
                    Reply(0x79, 0x01, 0x04, 0x40, 0x79);
                    break;
                case 0x11:
                    Reply(0x79);
                    romSub = 1;
                    break;
                default:
                    Reply(0x1F);
                    break;
                }
                return 2;
            }
        }

        // ---- front-panel socket ----

        public void StartPanel(int port)
        {
            if(listener != null) { return; }
            listener = new TcpListener(IPAddress.Loopback, port);
            listener.Start();
            var t = new Thread(AcceptLoop) { IsBackground = true, Name = "LPPM0 panel" };
            t.Start();
            this.Log(LogLevel.Info, "M0 front-panel socket on port {0}", port);
        }

        private void AcceptLoop()
        {
            while(true)
            {
                TcpClient c;
                try { c = listener.AcceptTcpClient(); }
                catch(Exception) { return; }
                c.NoDelay = true;
                var stream = c.GetStream();
                lock(clientLock)
                {
                    try { client?.Close(); } catch(Exception) { }
                    client = c;
                    clientStream = stream;
                }
                var sb = new StringBuilder();
                for(var hw = 0; hw < LedCount; hw++)
                {
                    var v = leds[hw];
                    if(v != 0) { sb.Append("l ").Append(hw).Append(' ').Append((v >> 16) & 0xFF).Append(' ').Append((v >> 8) & 0xFF).Append(' ').Append(v & 0xFF).Append('\n'); }
                }
                if(Frames >= 50) { sb.Append("up\n"); }
                Notify(sb);
                var reader = new Thread(() => ReadLoop(c, stream)) { IsBackground = true, Name = "LPPM0 panel rx" };
                reader.Start();
            }
        }

        private void ReadLoop(TcpClient c, NetworkStream stream)
        {
            try
            {
                using(var r = new StreamReader(stream, Encoding.ASCII))
                {
                    string line;
                    while((line = r.ReadLine()) != null)
                    {
                        var parts = line.Trim().Split(' ');
                        if(parts.Length == 3 && parts[0] == "p")
                        {
                            int ctrl, p;
                            if(int.TryParse(parts[1], out ctrl) && int.TryParse(parts[2], out p)) { Press(ctrl, p); }
                        }
                        else if(parts[0] == "?")
                        {
                            Notify("s " + Stats() + "\n");
                        }
                    }
                }
            }
            catch(Exception) { }
            lock(clientLock)
            {
                if(client == c) { client = null; clientStream = null; }
            }
        }

        private void Notify(StringBuilder sb)
        {
            if(sb.Length > 0) { Notify(sb.ToString()); }
        }

        private void Notify(string text)
        {
            if(text == "up") { text = "up\n"; }
            lock(clientLock)
            {
                if(clientStream == null) { return; }
                var bytes = Encoding.ASCII.GetBytes(text);
                try { clientStream.Write(bytes, 0, bytes.Length); }
                catch(Exception)
                {
                    try { client.Close(); } catch(Exception) { }
                    client = null; clientStream = null;
                }
            }
        }

        private const int MaxPressure = 0x0C40;
        private const int LedCount = 128;
        private static readonly byte[] OriginalVector = { 0xD8, 0x0D, 0x00, 0x20, 0x85, 0x26, 0x00, 0x08,
                                                          0x29, 0x24, 0x00, 0x08, 0x2B, 0x24, 0x00, 0x08 };

        private readonly IMachine machine;
        private readonly IUART uart;
        private readonly IUARTWithBufferState uartState;
        private readonly LimitTimer streamTimer;
        private readonly LimitTimer replyTimer;
        private readonly List<byte> pendingReplies = new List<byte>();
        private readonly byte[] frame = new byte[140];
        private readonly byte[] rx = new byte[512];
        private readonly int[] leds = new int[LedCount];
        private readonly Dictionary<int, byte[]> staged = new Dictionary<int, byte[]>();
        private readonly object clientLock = new object();
        private int rxCount;
        private int frameRequests;
        private bool rom;
        private int romSub;
        private uint romAddr;
        private ushort counter;
        private bool streaming;
        private TcpListener listener;
        private TcpClient client;
        private NetworkStream clientStream;
    }
}
