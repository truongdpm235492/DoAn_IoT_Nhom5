
import time


class LcdApi:
    def __init__(self, num_lines, num_columns):
        self.num_lines = num_lines
        self.num_columns = num_columns
        self.cursor_x = 0
        self.cursor_y = 0

    def clear(self):
        self.hal_write_command(0x01)
        time.sleep_ms(2)
        self.cursor_x = 0
        self.cursor_y = 0

    def move_to(self, cursor_x, cursor_y):
        self.cursor_x = cursor_x
        self.cursor_y = cursor_y

        addr = cursor_x & 0x3F

        if cursor_y & 1:
            addr += 0x40

        if cursor_y & 2:
            addr += self.num_columns

        self.hal_write_command(0x80 | addr)

    def putstr(self, string):
        for char in string:
            if char == '\n':
                self.move_to(0, self.cursor_y + 1)
            else:
                self.hal_write_data(ord(char))
                self.cursor_x += 1
