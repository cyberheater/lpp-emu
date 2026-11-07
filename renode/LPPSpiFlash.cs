// 16 MB SPI NOR flash (Macronix MX25L128-style, JEDEC C2 20 18) on SPI1 with chip select on a GPIO.
//
// Supports the 25-series command subset used by CoreFW (spi-memory) and typical vendor code:
//   9F JEDEC ID, 05 read status, 06/04 write enable/disable, 03 read, 0B fast read, 02 page program,
//   20 sector erase (4 KB), 52 / D8 block erase (32 / 64 KB), 60 / C7 chip erase, AB release power-down.
// Operations complete instantly (status BUSY never set). Page program wraps within the 256-byte page and can only
// clear bits, like real NOR flash.
//
// Contents persist in a file: `spiFlash UseFile @path` (created filled with 0xFF if missing; written through).
using System;
using System.IO;

using Antmicro.Renode.Core;
using Antmicro.Renode.Logging;
using Antmicro.Renode.Peripherals.SPI;

namespace Antmicro.Renode.Peripherals.SPI
{
    public sealed class LPPSpiFlash : ISPIPeripheral, IGPIOReceiver
    {
        public LPPSpiFlash()
        {
            for(var i = 0; i < data.Length; i++) { data[i] = 0xFF; }
        }

        public void Reset()
        {
            selected = false;
            pos = 0;
            wel = false;
        }

        public void UseFile(string path)
        {
            file?.Dispose();
            if(File.Exists(path))
            {
                var bytes = File.ReadAllBytes(path);
                Array.Copy(bytes, data, Math.Min(bytes.Length, data.Length));
            }
            file = new FileStream(path, FileMode.OpenOrCreate, FileAccess.ReadWrite);
            if(file.Length != Size)
            {
                file.SetLength(Size);
                file.Seek(0, SeekOrigin.Begin);
                file.Write(data, 0, data.Length);
                file.Flush();
            }
            this.Log(LogLevel.Info, "SPI flash backed by {0}", path);
        }

        /// GPIO 0 = chip select (active low).
        public void OnGPIO(int number, bool value)
        {
            if(number != 0) { return; }
            if(!value && !selected)
            {
                selected = true;
                pos = 0;
                cmd = 0;
            }
            else if(value && selected)
            {
                selected = false;
                EndCommand();
            }
        }

        public byte Transmit(byte b)
        {
            // Without a chip-select connection, treat every transfer as selected.
            byte result = 0xFF;
            if(pos == 0)
            {
                cmd = b;
                addr = 0;
                switch(cmd)
                {
                case 0x06: wel = true; break;
                case 0x04: wel = false; break;
                }
            }
            else
            {
                switch(cmd)
                {
                case 0x9F:
                    result = pos == 1 ? (byte)0xC2 : pos == 2 ? (byte)0x20 : pos == 3 ? (byte)0x18 : (byte)0x00;
                    break;
                case 0x05:
                    result = (byte)(wel ? 0x02 : 0x00);
                    break;
                case 0x03:
                case 0x0B:
                    if(pos <= 3) { addr = (addr << 8) | b; }
                    else if(cmd == 0x0B && pos == 4) { }     // dummy byte
                    else
                    {
                        result = data[addr & (Size - 1)];
                        addr++;
                    }
                    break;
                case 0x02:
                    if(pos <= 3) { addr = (addr << 8) | b; if(pos == 3) { pageStart = addr; } }
                    else if(wel)
                    {
                        var a = (int)((pageStart & ~0xFFu) | ((pageStart + (uint)(pos - 4)) & 0xFF)) & (Size - 1);
                        data[a] &= b;
                        Dirty(a, 1);
                    }
                    break;
                case 0x20:
                case 0x52:
                case 0xD8:
                    if(pos <= 3) { addr = (addr << 8) | b; }
                    break;
                }
            }
            pos++;
            return result;
        }

        public void FinishTransmission() { }

        private void EndCommand()
        {
            if(pos >= 4 && wel)
            {
                switch(cmd)
                {
                case 0x20: Erase(addr, 4096); break;
                case 0x52: Erase(addr, 32 * 1024); break;
                case 0xD8: Erase(addr, 64 * 1024); break;
                }
            }
            if(pos >= 1 && wel && (cmd == 0x60 || cmd == 0xC7)) { Erase(0, Size); }
            if(cmd == 0x02 || cmd == 0x20 || cmd == 0x52 || cmd == 0xD8 || cmd == 0x60 || cmd == 0xC7)
            {
                wel = false;
                Flush();
            }
            pos = 0;
        }

        private void Erase(uint at, int len)
        {
            var start = (int)(at & (Size - 1)) & ~(len - 1);
            for(var i = 0; i < len; i++) { data[start + i] = 0xFF; }
            Dirty(start, len);
            this.Log(LogLevel.Debug, "erase {0:X6} +{1:X}", start, len);
        }

        private void Dirty(int start, int len)
        {
            if(dirtyStart < 0) { dirtyStart = start; dirtyEnd = start + len; return; }
            dirtyStart = Math.Min(dirtyStart, start);
            dirtyEnd = Math.Max(dirtyEnd, start + len);
        }

        private void Flush()
        {
            if(file == null || dirtyStart < 0) { dirtyStart = -1; return; }
            file.Seek(dirtyStart, SeekOrigin.Begin);
            file.Write(data, dirtyStart, dirtyEnd - dirtyStart);
            file.Flush();
            dirtyStart = -1;
        }

        private const int Size = 16 * 1024 * 1024;
        private readonly byte[] data = new byte[Size];
        private FileStream file;
        private bool selected;
        private bool wel;
        private int pos;
        private byte cmd;
        private uint addr;
        private uint pageStart;
        private int dirtyStart = -1;
        private int dirtyEnd;
    }
}
