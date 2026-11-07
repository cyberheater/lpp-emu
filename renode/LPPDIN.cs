// Launchpad Pro MK3 DIN MIDI jacks, bridged to a TCP socket (StartBridge <port>).
//
// Stock 4.40 drives DIN Out 1 + DIN In on UART4 and DIN Out 2 on UART7 (both 31250 baud; it mirrors its output to
// both outs). Bytes the firmware transmits are forwarded raw; bytes from the socket are fed into the input UART,
// which paces them at its baud rate in virtual time.
//
// Socket, text lines:  out "o <1|2> <hex bytes>"   in "i <hex bytes>"
using System;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;

using Antmicro.Renode.Core;
using Antmicro.Renode.Logging;
using Antmicro.Renode.Peripherals.Bus;

namespace Antmicro.Renode.Peripherals.UART
{
    public sealed class LPPDIN : IDoubleWordPeripheral, IKnownSize
    {
        public LPPDIN(IMachine machine, IUART out1, IUART out2, IUART input)
        {
            this.input = input;
            out1.CharReceived += b => Forward(1, b);
            if(out2 != null && out2 != out1) { out2.CharReceived += b => Forward(2, b); }
        }

        public void Reset() { }
        public long Size => 0x10;
        public uint ReadDoubleWord(long offset) => offset == 0 ? (uint)BytesOut : offset == 4 ? (uint)BytesIn : 0;
        public void WriteDoubleWord(long offset, uint value) { }

        public ulong BytesOut { get; private set; }
        public ulong BytesIn { get; private set; }

        private void Forward(int port, byte b)
        {
            BytesOut++;
            Send("o " + port + " " + b.ToString("x2") + "\n");
        }

        public void StartBridge(int port)
        {
            if(listener != null) { return; }
            listener = new TcpListener(IPAddress.Loopback, port);
            listener.Start();
            new Thread(AcceptLoop) { IsBackground = true, Name = "LPPDIN bridge" }.Start();
            this.Log(LogLevel.Info, "DIN MIDI bridge on port {0}", port);
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
                var stream = c.GetStream();
                new Thread(() => ReadLoop(c, stream)) { IsBackground = true, Name = "LPPDIN bridge rx" }.Start();
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
                        var f = line.Trim().Split(' ');
                        if(f.Length < 2 || f[0] != "i") { continue; }
                        for(var k = 1; k < f.Length; k++)
                        {
                            byte b;
                            if(byte.TryParse(f[k], System.Globalization.NumberStyles.HexNumber, null, out b))
                            {
                                input.WriteChar(b);
                                BytesIn++;
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

        private readonly IUART input;
        private readonly object clientLock = new object();
        private TcpListener listener;
        private TcpClient client;
        private NetworkStream clientStream;
    }
}
