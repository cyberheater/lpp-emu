// STM32F7 USB OTG FS core (Synopsys DWC2) in device mode, with a built-in USB host.
//
// The host side plays the part of the Mac: it resets the bus, enumerates the firmware (device, configuration
// and jack-name strings), selects the configuration and then moves USB-MIDI 4-byte event packets between the
// firmware's bulk endpoints and a TCP bridge socket (StartBridge <port>), in virtual time.
//
// Modelled: slave (FIFO) mode only, no DMA; RX FIFO status/data queue (GRXSTSR/GRXSTSP + FIFO reads), per-endpoint
// TX FIFOs, DIEPINT/DOEPINT/DAINT/GINTSTS interrupt tree incl. TXFE via DIEPEMPMSK, EPDIS, global NAK handshakes,
// GRSTCTL self-clearing resets, DSTS full speed. Enough for ST's HAL PCD driver and CoreFW's otg_fs.rs.
//
// Bridge socket, text lines:
//   out: "dev <vid> <pid> <product>"   "cable in <n> <name>" (firmware -> host jacks)   "cable out <n> <name>"
//        "ready" (configured)          "m <8 hex>" one USB-MIDI packet from the firmware   "log <text>"
//   in : "m <8 hex>"                    one USB-MIDI packet to the firmware (cable number in the high nibble)
using System;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;

using Antmicro.Renode.Core;
using Antmicro.Renode.Core.Structure;
using Antmicro.Renode.Logging;
using Antmicro.Renode.Peripherals.Bus;
using Antmicro.Renode.Peripherals.Timers;
using Antmicro.Renode.Time;

namespace Antmicro.Renode.Peripherals.USB
{
    public sealed class LPPOTGFS : IDoubleWordPeripheral, IKnownSize
    {
        public LPPOTGFS(IMachine machine)
        {
            IRQ = new GPIO();
            tick = new LimitTimer(machine.ClockSource, 1000000, this, "usbhost", limit: TickUs,
                direction: Direction.Ascending, enabled: true, eventEnabled: true, autoUpdate: true,
                workMode: WorkMode.Periodic);
            tick.LimitReached += OnTick;
            Reset();
        }

        public GPIO IRQ { get; }
        public long Size => 0x40000;

        public void Reset()
        {
            Array.Clear(regs, 0, regs.Length);
            CoreReset();
            hostState = HostState.Detached;
            stateTime = 0;
            now = 0;
            ctrlQueue.Clear();
            ctrl = null;
            midiInEp = midiOutEp = -1;
            configured = false;
            outQueue.Clear();
            Update();
        }

        public string Status => string.Format("{0} cfg={1} in={2} out={3} ctrl={4}", hostState, configured, PacketsIn, PacketsOut, ctrl == null ? "-" : ctrl.Name);
        public ulong PacketsIn { get; private set; }
        public ulong PacketsOut { get; private set; }

        // ======================= register interface =======================

        public uint ReadDoubleWord(long offset)
        {
            if(offset >= 0x1000 && offset < 0x11000) { return PopRxWord(); }
            if(offset >= 0x20000) { return 0; }
            switch(offset)
            {
            case GOTGCTL: return (regs[offset >> 2] & 0xFFFF) | 0x000D0000;     // CIDSTS=B, A/B session valid
            case GRSTCTL: return 0x80000000;                                     // AHBIDL; resets complete at once
            case GINTSTS: return GintSts();
            case GRXSTSR: return rxQueue.Count > 0 ? rxQueue.Peek().Status : 0;
            case GRXSTSP: return PopRxStatus();
            case GNPTXSTS: return (8u << 16) | TxFree(0);
            case GSNPSID: return 0x4F54320A;
            case DSTS: return (3u << 1) | (((uint)now & 0x3FFF) << 8);         // full speed, frame number
            case DAINT: return Daint();
            }
            if(offset >= DIEPBASE && offset < DIEPBASE + 0x20 * EpCount)
            {
                var ep = (int)((offset - DIEPBASE) >> 5);
                switch(offset & 0x1F)
                {
                case 0x08: return DiepInt(ep);
                case 0x18: return TxFree(ep);
                }
            }
            if(offset >= DOEPBASE && offset < DOEPBASE + 0x20 * EpCount && (offset & 0x1F) == 0x08)
            {
                return regs[offset >> 2];
            }
            return offset < RegSpace ? regs[offset >> 2] : 0;
        }

        public void WriteDoubleWord(long offset, uint value)
        {
            if(offset >= 0x1000 && offset < 0x11000)
            {
                PushTxWord((int)((offset - 0x1000) >> 12), value);
                return;
            }
            if(offset >= RegSpace) { return; }
            var i = offset >> 2;
            switch(offset)
            {
            case GRSTCTL:
                if((value & 1) != 0) { CoreReset(); }
                if((value & 0x10) != 0) { rxQueue.Clear(); currentRx = null; }
                if((value & 0x20) != 0)
                {
                    var n = (int)((value >> 6) & 0x1F);
                    for(var ep = 0; ep < EpCount; ep++) { if(n == 0x10 || n == ep) { txFifo[ep].Clear(); } }
                }
                break;
            case GINTSTS:
                gintsts &= ~(value & GintW1C);
                break;
            case GOTGINT:
                regs[i] &= ~value;
                break;
            case DCTL:
                regs[i] = value & ~0xF80u;                                        // SGINAK..CGONAK are write-only
                if((value & (1 << 7)) != 0) { gintsts |= 1u << 6; }               // SGINAK -> GINAKEFF
                if((value & (1 << 8)) != 0) { gintsts &= ~(1u << 6); }            // CGINAK
                if((value & (1 << 9)) != 0) { gintsts |= 1u << 7; }               // SGONAK -> GONAKEFF
                if((value & (1 << 10)) != 0) { gintsts &= ~(1u << 7); }           // CGONAK
                break;
            default:
                if(offset >= DIEPBASE && offset < DIEPBASE + 0x20 * EpCount)
                {
                    WriteEp(true, (int)((offset - DIEPBASE) >> 5), (int)(offset & 0x1F), value);
                }
                else if(offset >= DOEPBASE && offset < DOEPBASE + 0x20 * EpCount)
                {
                    WriteEp(false, (int)((offset - DOEPBASE) >> 5), (int)(offset & 0x1F), value);
                }
                else
                {
                    regs[i] = value;
                }
                break;
            }
            Pump();
            Update();
        }

        private void WriteEp(bool isIn, int ep, int reg, uint value)
        {
            var i = ((isIn ? DIEPBASE : DOEPBASE) + ep * 0x20 + reg) >> 2;
            switch(reg)
            {
            case 0x00: // DxEPCTL: CNAK/SNAK/SD0PID/SD1PID are write-only
            {
                var old = regs[i];
                var v = value & ~((1u << 26) | (1u << 27) | (1u << 28) | (1u << 29));
                if((value & (1u << 27)) != 0) { v |= 1u << 17; }                  // SNAK -> NAKSTS
                else if((value & (1u << 26)) != 0) { v &= ~(1u << 17); }           // CNAK
                else { v = (v & ~(1u << 17)) | (old & (1u << 17)); }
                if((value & (1u << 30)) != 0)                                       // EPDIS
                {
                    v &= ~((1u << 30) | (1u << 31));
                    regs[i + 2] |= 1u << 1;                                         // EPDISD
                    if(isIn) { txFifo[ep].Clear(); }
                }
                regs[i] = v;
                if(ep == 0 && (v & (1u << 21)) != 0 && ctrl != null) { ctrlStalled = true; }
                break;
            }
            case 0x08: // DxEPINT, write 1 to clear
                regs[i] &= ~value;
                break;
            default:
                regs[i] = value;
                break;
            }
        }

        // ======================= interrupt tree =======================

        private uint DiepInt(int ep)
        {
            var v = regs[(DIEPBASE + ep * 0x20 + 8) >> 2] & ~(1u << 7);
            if(txFifo[ep].Count == 0) { v |= 1u << 7; }                             // TXFE (FIFO empty)
            return v;
        }

        private uint Daint()
        {
            uint d = 0;
            var diepmsk = regs[DIEPMSK >> 2];
            var doepmsk = regs[DOEPMSK >> 2];
            var empmsk = regs[DIEPEMPMSK >> 2];
            for(var ep = 0; ep < EpCount; ep++)
            {
                var m = diepmsk | (((empmsk >> ep) & 1) << 7);
                if((DiepInt(ep) & m) != 0) { d |= 1u << ep; }
                if((regs[(DOEPBASE + ep * 0x20 + 8) >> 2] & doepmsk) != 0) { d |= 1u << (16 + ep); }
            }
            return d;
        }

        private uint GintSts()
        {
            var v = gintsts;
            if(rxQueue.Count > 0) { v |= 1u << 4; }                                 // RXFLVL
            var d = Daint() & regs[DAINTMSK >> 2];
            if((d & 0xFFFF) != 0) { v |= 1u << 18; }                                // IEPINT
            if((d & 0xFFFF0000) != 0) { v |= 1u << 19; }                            // OEPINT
            return v;                                                                // CMOD = 0: device
        }

        private void Update()
        {
            var on = (regs[GAHBCFG >> 2] & 1) != 0 && (GintSts() & regs[GINTMSK >> 2]) != 0;
            IRQ.Set(on);
        }

        private void CoreReset()
        {
            gintsts = 0;
            rxQueue.Clear();
            currentRx = null;
            for(var ep = 0; ep < EpCount; ep++) { txFifo[ep].Clear(); }
        }

        // ======================= RX FIFO (host -> firmware) =======================

        private sealed class RxEntry
        {
            public uint Status;
            public byte[] Data;
            public int Pos;
        }

        private void QueueRx(int ep, int pktsts, byte[] data)
        {
            var len = data == null ? 0 : data.Length;
            rxQueue.Enqueue(new RxEntry { Status = (uint)ep | ((uint)len << 4) | ((uint)pktsts << 17), Data = data ?? new byte[0] });
        }

        private uint PopRxStatus()
        {
            if(rxQueue.Count == 0) { return 0; }
            var e = rxQueue.Dequeue();
            currentRx = e;
            var ep = (int)(e.Status & 0xF);
            var pktsts = (int)((e.Status >> 17) & 0xF);
            var bcnt = (int)((e.Status >> 4) & 0x7FF);
            var doepint = (DOEPBASE + ep * 0x20 + 8) >> 2;
            var doeptsiz = (DOEPBASE + ep * 0x20 + 0x10) >> 2;
            switch(pktsts)
            {
            case 2: // OUT data packet
            {
                var t = regs[doeptsiz];
                var xfr = Math.Max(0, (int)(t & 0x7FFFF) - bcnt);
                var pkt = Math.Max(0, (int)((t >> 19) & 0x3FF) - 1);
                regs[doeptsiz] = (t & 0xE0000000) | ((uint)pkt << 19) | (uint)xfr;
                break;
            }
            case 3: // OUT transfer completed
                regs[doepint] |= 1u;                                                 // XFRC
                regs[(DOEPBASE + ep * 0x20) >> 2] &= ~(1u << 31);                    // EPENA off
                if(ep == 0 && ctrl != null && ctrl.Stage == Stage.StatusOutSent) { FinishControl(true); }
                break;
            case 4: // SETUP stage done
                regs[doepint] |= 1u << 3;                                            // STUP
                break;
            case 6: // SETUP data
            {
                var t = regs[doeptsiz];
                var cnt = Math.Max(0, (int)((t >> 29) & 3) - 1);
                regs[doeptsiz] = (t & ~(3u << 29)) | ((uint)cnt << 29);
                break;
            }
            }
            Update();
            return e.Status;
        }

        private uint PopRxWord()
        {
            var e = currentRx;
            if(e == null || e.Pos >= e.Data.Length) { return 0; }
            uint w = 0;
            for(var k = 0; k < 4 && e.Pos < e.Data.Length; k++) { w |= (uint)e.Data[e.Pos++] << (8 * k); }
            return w;
        }

        // ======================= TX FIFOs (firmware -> host) =======================

        private uint TxFree(int ep)
        {
            uint depth;
            if(ep == 0) { depth = regs[DIEPTXF0 >> 2] >> 16; }
            else { depth = regs[(DIEPTXF1 + (ep - 1) * 4) >> 2] >> 16; }
            if(depth == 0) { depth = 0x40; }
            var used = (uint)(txFifo[ep].Count + 3) / 4;
            return used >= depth ? 0 : depth - used;
        }

        private void PushTxWord(int ep, uint value)
        {
            if(ep >= EpCount) { return; }
            var q = txFifo[ep];
            q.Add((byte)value); q.Add((byte)(value >> 8)); q.Add((byte)(value >> 16)); q.Add((byte)(value >> 24));
            TakeIn(ep);
            Update();
        }

        private int Mps(bool isIn, int ep)
        {
            var c = regs[((isIn ? DIEPBASE : DOEPBASE) + ep * 0x20) >> 2];
            if(ep == 0)
            {
                switch(c & 3) { case 0: return 64; case 1: return 32; case 2: return 16; default: return 8; }
            }
            var m = (int)(c & 0x7FF);
            return m == 0 ? 64 : m;
        }

        /// The host issues IN tokens: take whole packets the firmware has queued on an enabled IN endpoint.
        private void TakeIn(int ep)
        {
            var ctlI = (DIEPBASE + ep * 0x20) >> 2;
            var sizI = ctlI + 4;
            while((regs[ctlI] & (1u << 31)) != 0)
            {
                var t = regs[sizI];
                var rem = (int)(t & 0x7FFFF);
                var pkts = (int)((t >> 19) & 0x3FF);
                if(pkts == 0 && rem == 0) { CompleteIn(ep); return; }
                var len = Math.Min(rem, Mps(true, ep));
                var padded = (len + 3) & ~3;
                var q = txFifo[ep];
                if(q.Count < padded) { return; }
                var pkt = q.GetRange(0, len).ToArray();
                q.RemoveRange(0, padded);
                rem -= len;
                pkts = Math.Max(0, pkts - 1);
                regs[sizI] = (t & 0xE0000000) | ((uint)pkts << 19) | (uint)rem;
                OnInPacket(ep, pkt);
                if(rem == 0 || pkts == 0 || len < Mps(true, ep)) { CompleteIn(ep); return; }
            }
        }

        private void CompleteIn(int ep)
        {
            var ctlI = (DIEPBASE + ep * 0x20) >> 2;
            regs[ctlI] &= ~(1u << 31);
            regs[ctlI + 2] |= 1u;                                                    // XFRC
        }

        // ======================= host =======================

        private enum HostState { Detached, Attaching, InReset, Enumerating, Running, Failed }
        private enum Stage { Pending, DataIn, StatusIn, StatusOut, StatusOutSent }

        private sealed class Control
        {
            public string Name;
            public byte[] Setup;
            public int Length;
            public bool In;
            public Stage Stage;
            public List<byte> Data = new List<byte>();
            public Action<bool, byte[]> Done;
            public ulong Started;
        }

        private void Request(string name, byte bmRequestType, byte bRequest, int wValue, int wIndex, int wLength, Action<bool, byte[]> done)
        {
            ctrlQueue.Enqueue(new Control
            {
                Name = name,
                Setup = new byte[] { bmRequestType, bRequest, (byte)wValue, (byte)(wValue >> 8), (byte)wIndex, (byte)(wIndex >> 8), (byte)wLength, (byte)(wLength >> 8) },
                Length = wLength,
                In = (bmRequestType & 0x80) != 0,
                Done = done
            });
        }

        private void OnTick()
        {
            now++;
            var connected = (regs[GAHBCFG >> 2] & 1) != 0 && (regs[DCTL >> 2] & 2) == 0 && (regs[GINTMSK >> 2] & (1u << 12)) != 0;
            if(!connected && hostState != HostState.Detached)
            {
                Log("device disconnected");
                hostState = HostState.Detached;
                configured = false;
                ctrl = null;
                ctrlQueue.Clear();
            }
            switch(hostState)
            {
            case HostState.Detached:
                if(connected) { hostState = HostState.Attaching; stateTime = now; }
                break;
            case HostState.Attaching:
                if(now - stateTime >= 50)
                {
                    Log("bus reset");
                    gintsts |= 1u << 12;                                             // USBRST
                    hostState = HostState.InReset;
                    stateTime = now;
                }
                break;
            case HostState.InReset:
                if(now - stateTime >= 10)
                {
                    gintsts |= 1u << 13;                                             // ENUMDNE
                    hostState = HostState.Enumerating;
                    stateTime = now;
                    StartEnumeration();
                }
                break;
            }
            if(ctrl != null && now - ctrl.Started > 500)
            {
                Log("control request " + ctrl.Name + " timed out in " + ctrl.Stage);
                FinishControl(false);
            }
            Pump();
            Update();
        }

        private void Pump()
        {
            if(hostState != HostState.Enumerating && hostState != HostState.Running) { return; }
            if(now - stateTime < 10) { return; }
            // control transfers
            // (a real core always accepts SETUP; STUPCNT only counts buffered ones, so it is not a gate)
            if(ctrl == null && ctrlQueue.Count > 0)
            {
                ctrl = ctrlQueue.Dequeue();
                ctrl.Started = now;
                ctrlStalled = false;
                regs[DIEPCTL0 >> 2] &= ~(1u << 21);                                  // a SETUP clears EP0 STALL
                regs[DOEPCTL0 >> 2] &= ~(1u << 21);
                QueueRx(0, 6, ctrl.Setup);
                QueueRx(0, 4, null);
                ctrl.Stage = ctrl.In && ctrl.Length > 0 ? Stage.DataIn : (ctrl.Length > 0 ? Stage.StatusIn : Stage.StatusIn);
            }
            if(ctrl != null && ctrlStalled)
            {
                Log("control request " + ctrl.Name + " stalled");
                FinishControl(false);
                return;
            }
            if(ctrl != null && ctrl.Stage == Stage.StatusOut && (regs[DOEPCTL0 >> 2] & (1u << 31)) != 0 && !RxPendingFor(0))
            {
                QueueRx(0, 2, null);
                QueueRx(0, 3, null);
                ctrl.Stage = Stage.StatusOutSent;
            }
            // MIDI OUT (host -> firmware)
            if(configured && midiOutEp > 0)
            {
                var ctlI = (DOEPBASE + midiOutEp * 0x20) >> 2;
                if((regs[ctlI] & (1u << 31)) != 0 && !RxPendingFor(midiOutEp))
                {
                    byte[] chunk = null;
                    lock(outQueue)
                    {
                        var n = Math.Min(outQueue.Count, Mps(false, midiOutEp)) & ~3;
                        if(n > 0) { chunk = outQueue.GetRange(0, n).ToArray(); outQueue.RemoveRange(0, n); }
                    }
                    if(chunk != null)
                    {
                        QueueRx(midiOutEp, 2, chunk);
                        QueueRx(midiOutEp, 3, null);
                        PacketsOut += (ulong)(chunk.Length / 4);
                    }
                }
            }
            for(var ep = 0; ep < EpCount; ep++) { TakeIn(ep); }
        }

        private bool RxPendingFor(int ep)
        {
            foreach(var e in rxQueue) { if((e.Status & 0xF) == ep) { return true; } }
            return false;
        }

        private void OnInPacket(int ep, byte[] pkt)
        {
            if(ep == 0)
            {
                if(ctrl == null) { return; }
                if(ctrl.Stage == Stage.DataIn)
                {
                    ctrl.Data.AddRange(pkt);
                    if(pkt.Length < Mps(true, 0) || ctrl.Data.Count >= ctrl.Length) { ctrl.Stage = Stage.StatusOut; }
                }
                else if(ctrl.Stage == Stage.StatusIn && pkt.Length == 0)
                {
                    FinishControl(true);
                }
                return;
            }
            if(ep == midiInEp && configured)
            {
                var sb = new StringBuilder();
                for(var k = 0; k + 3 < pkt.Length; k += 4)
                {
                    if(pkt[k] == 0 && pkt[k + 1] == 0 && pkt[k + 2] == 0 && pkt[k + 3] == 0) { continue; }
                    sb.Append("m ").Append(pkt[k].ToString("x2")).Append(pkt[k + 1].ToString("x2"))
                      .Append(pkt[k + 2].ToString("x2")).Append(pkt[k + 3].ToString("x2")).Append('\n');
                    PacketsIn++;
                }
                Send(sb.ToString());
            }
        }

        private void FinishControl(bool ok)
        {
            var c = ctrl;
            ctrl = null;
            if(c == null) { return; }
            try { c.Done?.Invoke(ok, c.Data.ToArray()); }
            catch(Exception e) { Log("enumeration error in " + c.Name + ": " + e.Message); }
        }

        // ----- enumeration -----

        private void StartEnumeration()
        {
            configured = false;
            midiInEp = midiOutEp = -1;
            cablesIn.Clear(); cablesOut.Clear();
            Request("GET_DESCRIPTOR(device, 64)", 0x80, 6, 0x0100, 0, 64, (ok, d) =>
            {
                if(!ok || d.Length < 8) { Fail("no device descriptor"); return; }
                Request("SET_ADDRESS(1)", 0x00, 5, 1, 0, 0, (ok2, _) =>
                {
                    if(!ok2) { Fail("SET_ADDRESS failed"); return; }
                    Log("address " + ((regs[DCFG >> 2] >> 4) & 0x7F));
                    Request("GET_DESCRIPTOR(device)", 0x80, 6, 0x0100, 0, 18, (ok3, dev) =>
                    {
                        if(!ok3 || dev.Length < 18) { Fail("short device descriptor"); return; }
                        vid = dev[8] | (dev[9] << 8);
                        pid = dev[10] | (dev[11] << 8);
                        var iProduct = dev[15];
                        Request("GET_DESCRIPTOR(config, 9)", 0x80, 6, 0x0200, 0, 9, (ok4, c9) =>
                        {
                            if(!ok4 || c9.Length < 9) { Fail("no configuration descriptor"); return; }
                            var total = c9[2] | (c9[3] << 8);
                            Request("GET_DESCRIPTOR(config)", 0x80, 6, 0x0200, 0, total, (ok5, cfg) =>
                            {
                                if(!ok5) { Fail("configuration descriptor failed"); return; }
                                ParseConfig(cfg);
                                Request("GET_DESCRIPTOR(string 0)", 0x80, 6, 0x0300, 0, 255, (ok6, langs) =>
                                {
                                    lang = ok6 && langs.Length >= 4 ? langs[2] | (langs[3] << 8) : 0x0409;
                                    GetString(iProduct, s => product = s ?? "");
                                    foreach(var j in jacks) { var jj = j; GetString(jj.StringIndex, s => jj.Name = s); }
                                    Request("SET_CONFIGURATION", 0x00, 9, cfg.Length > 5 ? cfg[5] : 1, 0, 0, (ok7, __) =>
                                    {
                                        if(!ok7) { Fail("SET_CONFIGURATION failed"); return; }
                                        configured = true;
                                        hostState = HostState.Running;
                                        Log(string.Format("configured {0:x4}:{1:x4} \"{2}\", MIDI IN ep {3}, OUT ep {4}", vid, pid, product, midiInEp, midiOutEp));
                                        Send(Announce());
                                    });
                                });
                            });
                        });
                    });
                });
            });
        }

        private void GetString(int index, Action<string> done)
        {
            if(index == 0) { done(null); return; }
            Request("GET_DESCRIPTOR(string " + index + ")", 0x80, 6, 0x0300 | index, lang, 255, (ok, d) =>
            {
                if(!ok || d.Length < 2) { done(null); return; }
                var n = Math.Min(d[0], d.Length);
                done(Encoding.Unicode.GetString(d, 2, Math.Max(0, n - 2)));
            });
        }

        private sealed class Jack { public int Id; public bool In; public int StringIndex; public string Name; }

        private void ParseConfig(byte[] cfg)
        {
            jacks.Clear();
            var inMidi = false;
            var lastEp = 0;
            for(var p = 0; p + 2 <= cfg.Length && cfg[p] >= 2; p += cfg[p])
            {
                var len = cfg[p];
                var type = cfg[p + 1];
                if(p + len > cfg.Length) { break; }
                if(type == 4 && len >= 9)                                            // interface
                {
                    inMidi = cfg[p + 5] == 1 && cfg[p + 6] == 3;                     // audio / MIDI streaming
                }
                else if(type == 5 && len >= 7 && inMidi && (cfg[p + 3] & 3) == 2)   // bulk endpoint
                {
                    lastEp = cfg[p + 2];
                    if((lastEp & 0x80) != 0) { if(midiInEp < 0) { midiInEp = lastEp & 0xF; } }
                    else if(midiOutEp < 0) { midiOutEp = lastEp & 0xF; }
                }
                else if(type == 0x24 && inMidi && len >= 6 && (cfg[p + 2] == 2 || cfg[p + 2] == 3) && cfg[p + 3] == 1)
                {
                    // embedded MIDI IN jack (host -> device) / MIDI OUT jack (device -> host)
                    var isInJack = cfg[p + 2] == 2;
                    var strIdx = isInJack ? cfg[p + 5] : cfg[p + len - 1];
                    jacks.Add(new Jack { Id = cfg[p + 4], In = isInJack, StringIndex = strIdx });
                }
                else if(type == 0x25 && inMidi && len >= 4 && cfg[p + 2] == 1)        // CS endpoint: jack list
                {
                    var list = (lastEp & 0x80) != 0 ? cablesIn : cablesOut;
                    for(var k = 0; k < cfg[p + 3] && p + 4 + k < p + len; k++) { list.Add(cfg[p + 4 + k]); }
                }
            }
        }

        private string Announce()
        {
            var sb = new StringBuilder();
            sb.AppendFormat("dev {0:x4} {1:x4} {2}\n", vid, pid, product);
            // cables are numbered by position in the endpoint's jack list
            for(var n = 0; n < cablesIn.Count; n++) { sb.AppendFormat("cable in {0} {1}\n", n, JackName(cablesIn[n], n)); }
            for(var n = 0; n < cablesOut.Count; n++) { sb.AppendFormat("cable out {0} {1}\n", n, JackName(cablesOut[n], n)); }
            sb.Append("ready\n");
            return sb.ToString();
        }

        private string JackName(int id, int n)
        {
            foreach(var j in jacks) { if(j.Id == id && !string.IsNullOrEmpty(j.Name)) { return j.Name; } }
            return "Port " + (n + 1);
        }

        private void Fail(string why)
        {
            Log("enumeration failed: " + why);
            hostState = HostState.Failed;
        }

        private void Log(string msg)
        {
            this.Log(LogLevel.Info, msg);
            Send("log " + msg + "\n");
        }

        // ======================= bridge socket =======================

        public void StartBridge(int port)
        {
            if(listener != null) { return; }
            listener = new TcpListener(IPAddress.Loopback, port);
            listener.Start();
            var t = new Thread(AcceptLoop) { IsBackground = true, Name = "LPPOTGFS bridge" };
            t.Start();
            this.Log(LogLevel.Info, "USB MIDI bridge on port {0}", port);
        }

        private void AcceptLoop()
        {
            while(true)
            {
                TcpClient c;
                try { c = listener.AcceptTcpClient(); }
                catch(Exception) { return; }
                c.NoDelay = true;
                lock(clientLock)
                {
                    try { client?.Close(); } catch(Exception) { }
                    client = c;
                    clientStream = c.GetStream();
                }
                if(configured) { Send(Announce()); }
                var stream = c.GetStream();
                var reader = new Thread(() => ReadLoop(c, stream)) { IsBackground = true, Name = "LPPOTGFS bridge rx" };
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
                        line = line.Trim();
                        if(line.Length == 10 && line[0] == 'm' && line[1] == ' ')
                        {
                            uint v;
                            if(uint.TryParse(line.Substring(2), System.Globalization.NumberStyles.HexNumber, null, out v))
                            {
                                lock(outQueue)
                                {
                                    if(outQueue.Count < 4096)
                                    {
                                        outQueue.Add((byte)(v >> 24)); outQueue.Add((byte)(v >> 16));
                                        outQueue.Add((byte)(v >> 8)); outQueue.Add((byte)v);
                                    }
                                }
                            }
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

        private void Send(string text)
        {
            if(string.IsNullOrEmpty(text)) { return; }
            lock(clientLock)
            {
                if(clientStream == null) { return; }
                var bytes = Encoding.UTF8.GetBytes(text);
                try { clientStream.Write(bytes, 0, bytes.Length); }
                catch(Exception)
                {
                    try { client.Close(); } catch(Exception) { }
                    client = null; clientStream = null;
                }
            }
        }

        // ======================= state =======================

        private const int EpCount = 6;
        private const ulong TickUs = 1000;
        private const long RegSpace = 0x1000;
        private const long GOTGCTL = 0x000, GOTGINT = 0x004, GAHBCFG = 0x008, GRSTCTL = 0x010, GINTSTS = 0x014,
            GINTMSK = 0x018, GRXSTSR = 0x01C, GRXSTSP = 0x020, DIEPTXF0 = 0x028, GNPTXSTS = 0x02C, GSNPSID = 0x040,
            DIEPTXF1 = 0x104, DCFG = 0x800, DCTL = 0x804, DSTS = 0x808, DIEPMSK = 0x810, DOEPMSK = 0x814,
            DAINT = 0x818, DAINTMSK = 0x81C, DIEPEMPMSK = 0x834, DIEPBASE = 0x900, DOEPBASE = 0xB00,
            DIEPCTL0 = 0x900, DOEPCTL0 = 0xB00, DOEPTSIZ0 = 0xB10;
        // GINTSTS bits cleared by writing 1
        private const uint GintW1C = (1u << 1) | (1u << 3) | (1u << 10) | (1u << 11) | (1u << 12) | (1u << 13) | (1u << 14) |
            (1u << 15) | (1u << 20) | (1u << 21) | (1u << 23) | (1u << 28) | (1u << 29) | (1u << 30) | (1u << 31);

        private readonly uint[] regs = new uint[RegSpace / 4];
        private uint gintsts;
        private readonly Queue<RxEntry> rxQueue = new Queue<RxEntry>();
        private RxEntry currentRx;
        private readonly List<byte>[] txFifo = { new List<byte>(), new List<byte>(), new List<byte>(), new List<byte>(), new List<byte>(), new List<byte>() };
        private readonly LimitTimer tick;
        private ulong now, stateTime;
        private HostState hostState;
        private readonly Queue<Control> ctrlQueue = new Queue<Control>();
        private Control ctrl;
        private bool ctrlStalled;
        private bool configured;
        private int midiInEp = -1, midiOutEp = -1;
        private int vid, pid, lang = 0x0409;
        private string product = "";
        private readonly List<Jack> jacks = new List<Jack>();
        private readonly List<int> cablesIn = new List<int>();
        private readonly List<int> cablesOut = new List<int>();
        private readonly List<byte> outQueue = new List<byte>();
        private readonly object clientLock = new object();
        private TcpListener listener;
        private TcpClient client;
        private NetworkStream clientStream;
    }
}
