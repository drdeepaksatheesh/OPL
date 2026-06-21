# acquisition/npg_lite.py

from acquisition.transports.serial_transport import SerialTransport
import time


class NPGLite:
    def __init__(self, port="COM3", baudrate=230400):
        self.transport = SerialTransport(
            port=port,
            baudrate=baudrate,
            timeout=1
        )

    def connect(self):
        self.transport.connect()

    def disconnect(self):
        self.transport.disconnect()

    def identify(self):
        return self.transport.command_response("WHOAREYOU")

    def status(self):
        return self.transport.command_response("STATUS")

    def set_rate(self, rate_hz):
        return self.transport.command_response(f"SETRATE {rate_hz}")

    def set_channels(self, channels):
        return self.transport.command_response(f"SETCH {channels}")

    def start_streaming(self):
        """
        Send START and wait for STARTED + header.
        """
        self.transport.flush()
        self.transport.write_line("START")

        responses = []
        start_time = time.time()

        while time.time() - start_time < 2:
            line = self.transport.read_line()

            if line:
                responses.append(line)

                if line.startswith("sample,time_us"):
                    break

        return responses

    def stop_streaming(self):
        """
        Send STOP and wait until STOPPED is actually received.
        During streaming, sample lines may still arrive before STOPPED.
        """
        self.transport.write_line("STOP")

        responses = []
        start_time = time.time()

        while time.time() - start_time < 3:
            line = self.transport.read_line()

            if line:
                responses.append(line)

                if line == "STOPPED":
                    break

        return responses

    def read_sample_line(self):
        """
        Read one line from the serial stream.
        """
        return self.transport.read_line()

    def parse_sample_line(self, line):
        """
        Convert one CSV line into a dictionary.

        Expected:
        sample,time_us,ch1,ch2,ch3,ch4,ch5,ch6

        Blank inactive channels become None.
        """
        parts = line.strip().split(",")

        if len(parts) != 8:
            return None

        try:
            sample = int(parts[0])
            time_us = int(parts[1])

            channels = []

            for value in parts[2:]:
                if value == "":
                    channels.append(None)
                else:
                    channels.append(int(value))

            return {
                "sample": sample,
                "time_us": time_us,
                "ch1": channels[0],
                "ch2": channels[1],
                "ch3": channels[2],
                "ch4": channels[3],
                "ch5": channels[4],
                "ch6": channels[5],
            }

        except ValueError:
            return None


if __name__ == "__main__":
    device = NPGLite(port="COM3", baudrate=230400)

    try:
        device.connect()

        print("WHOAREYOU:")
        print(device.identify())

        print("STATUS:")
        print(device.status())

        print("Set rate:")
        print(device.set_rate(500))

        print("Set channels:")
        print(device.set_channels(1))

        print("START:")
        print(device.start_streaming())

        print("Reading 10 parsed sample lines:")

        lines_read = 0

        while lines_read < 10:
            line = device.read_sample_line()
            parsed = device.parse_sample_line(line)

            if parsed is not None:
                print(parsed)
                lines_read += 1

        print("STOP:")
        stop_response = device.stop_streaming()
        print(stop_response)

    finally:
        device.disconnect()