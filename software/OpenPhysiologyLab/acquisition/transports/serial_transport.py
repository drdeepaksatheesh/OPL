# acquisition/transports/serial_transport.py

import time
import serial
import serial.tools.list_ports


class SerialTransport:
    """
    Generic USB serial transport layer.

    This file does NOT know ECG, EMG, EEG, or NPG-specific details.
    It only knows how to:
    - list ports
    - connect
    - disconnect
    - send text commands
    - read serial lines
    """

    def __init__(self, port=None, baudrate=230400, timeout=1):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser = None

    @staticmethod
    def list_ports():
        ports = serial.tools.list_ports.comports()

        result = []

        for port in ports:
            result.append({
                "device": port.device,
                "description": port.description,
                "hwid": port.hwid
            })

        return result

    def connect(self):
        if self.port is None:
            raise ValueError("No COM port selected.")

        self.ser = serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            timeout=self.timeout
        )

        # Small delay after opening ESP32 serial
        time.sleep(2)

        self.flush()

        return True

    def disconnect(self):
        if self.ser is not None and self.ser.is_open:
            self.ser.close()

        self.ser = None

    def is_connected(self):
        return self.ser is not None and self.ser.is_open

    def flush(self):
        if not self.is_connected():
            return

        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()

    def write_line(self, text):
        if not self.is_connected():
            raise RuntimeError("Serial port is not connected.")

        message = text.strip() + "\n"
        self.ser.write(message.encode("utf-8"))

    def read_line(self):
        if not self.is_connected():
            raise RuntimeError("Serial port is not connected.")

        raw = self.ser.readline()

        return raw.decode("utf-8", errors="ignore").strip()

    def read_available_lines(self, max_lines=100):
        if not self.is_connected():
            raise RuntimeError("Serial port is not connected.")

        lines = []

        count = 0

        while self.ser.in_waiting > 0 and count < max_lines:
            line = self.read_line()

            if line:
                lines.append(line)

            count += 1

        return lines

    def command_response(self, command, wait_time=0.2, max_lines=50):
        self.write_line(command)

        time.sleep(wait_time)

        return self.read_available_lines(max_lines=max_lines)


if __name__ == "__main__":
    print("Available serial ports:")

    ports = SerialTransport.list_ports()

    for port in ports:
        print(port)

    print("\nserial_transport.py test completed.")