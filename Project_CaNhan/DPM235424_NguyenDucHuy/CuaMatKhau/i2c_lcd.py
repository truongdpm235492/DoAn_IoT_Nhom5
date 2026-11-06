class LcdApi:
    LCD_CLEARDISPLAY = 0x01
    LCD_RETURNHOME = 0x02
    LCD_ENTRYMODESET = 0x04
    LCD_DISPLAYCONTROL = 0x08
    LCD_CURSORSHIFT = 0x10
    LCD_FUNCTIONSET = 0x20
    LCD_SETCGRAMADDR = 0x40
    LCD_SETDDRAMADDR = 0x80

    LCD_ENTRYRIGHT = 0x00
    LCD_ENTRYLEFT = 0x02
    LCD_ENTRYSHIFTINCREMENT = 0x01
    LCD_ENTRYSHIFTDECREMENT = 0x00

    LCD_DISPLAYON = 0x04
    LCD_DISPLAYOFF = 0x00
    LCD_CURSORON = 0x02
    LCD_CURSOROFF = 0x00
    LCD_BLINKON = 0x01
    LCD_BLINKOFF = 0x00

    LCD_MOVELEFT = 0x00
    LCD_MOVERIGHT = 0x04
    LCD_DISPLAYMOVE = 0x08
    LCD_CURSORMOVE = 0x00

    LCD_2LINE = 0x08
    LCD_1LINE = 0x00
    LCD_5x10DOTS = 0x04
    LCD_5x8DOTS = 0x00

    LCD_BACKLIGHT = 0x08
    LCD_NOBACKLIGHT = 0x00

    LCD_READ_BIT = 0x04
    LCD_RW = 0x02
    LCD_RS = 0x01

    def __init__(self, num_lines, num_columns):
        self.num_lines = num_lines
        self.num_columns = num_columns
        self.cursor_x = 0
        self.cursor_y = 0
        self.impl_clear()
        self.impl_display_on_off(True, False, False)
        self.impl_entry_mode(True, False)
        self.backlight = True

    def clear(self):
        self.impl_write_command(self.LCD_CLEARDISPLAY)
        self.cursor_x = 0
        self.cursor_y = 0

    def home(self):
        self.impl_write_command(self.LCD_RETURNHOME)
        self.cursor_x = 0
        self.cursor_y = 0

    def set_cursor(self, col, row):
        if row >= self.num_lines:
            row = self.num_lines - 1
        if col >= self.num_columns:
            col = self.num_columns - 1
        self.cursor_x = col
        self.cursor_y = row
        addr = col & 0x3f
        if row & 1:
            addr += 0x40
        if row & 2:
            addr += 20
        self.impl_write_command(self.LCD_SETDDRAMADDR | addr)

    # Thêm hàm move_to để tương thích hoàn toàn với main.py của bạn
    def move_to(self, col, row):
        self.set_cursor(col, row)

    def putchar(self, char):
        if isinstance(char, str):
            char = ord(char)
        if char == 10:
            self.cursor_y += 1
            self.cursor_x = 0
            if self.cursor_y >= self.num_lines:
                self.cursor_y = 0
            self.set_cursor(self.cursor_x, self.cursor_y)
        else:
            self.impl_write_data(char)
            self.cursor_x += 1
            if self.cursor_x >= self.num_columns:
                self.cursor_x = 0
                self.cursor_y += 1
                if self.cursor_y >= self.num_lines:
                    self.cursor_y = 0
                self.set_cursor(self.cursor_x, self.cursor_y)

    def putstr(self, string):
        for char in string:
            self.putchar(char)


class I2cLcd(LcdApi):
    def __init__(self, i2c, i2c_addr, num_lines, num_columns):
        self.i2c = i2c
        self.i2c_addr = i2c_addr
        import time
        time.sleep_ms(20)
        self.i2c.writeto(self.i2c_addr, b'\x00')
        time.sleep_ms(20)
        
        # Khởi tạo chế độ 4-bit
        self.hal_write_init_nibble(0x30)
        time.sleep_ms(5)
        self.hal_write_init_nibble(0x30)
        time.sleep_ms(1)
        self.hal_write_init_nibble(0x30)
        self.hal_write_init_nibble(0x20)

        super().__init__(num_lines, num_columns)
        self.impl_write_command(0x28) 
        self.impl_write_command(0x0C) 
        self.impl_write_command(0x06) 
        self.clear()

    def hal_write_init_nibble(self, nibble):
        import time
        byte = (nibble & 0xF0) | 0x08 
        self.i2c.writeto(self.i2c_addr, bytes([byte | 0x04]))
        time.sleep_us(1)
        self.i2c.writeto(self.i2c_addr, bytes([byte & ~0x04]))
        time.sleep_us(50)

    def hal_backlight(self, on):
        pass

    def impl_write_command(self, cmd):
        self.hal_write(cmd, 0)

    def impl_write_data(self, data):
        self.hal_write(data, 1)

    def hal_write(self, val, mode):
        import time
        high = (val & 0xF0) | 0x08 | (mode & 0x01)
        low = ((val << 4) & 0xF0) | 0x08 | (mode & 0x01)
        
        self.i2c.writeto(self.i2c_addr, bytes([high | 0x04]))
        time.sleep_us(1)
        self.i2c.writeto(self.i2c_addr, bytes([high & ~0x04]))
        
        self.i2c.writeto(self.i2c_addr, bytes([low | 0x04]))
        time.sleep_us(1)
        self.i2c.writeto(self.i2c_addr, bytes([low & ~0x04]))

    def impl_clear(self):
        pass

    def impl_display_on_off(self, display, cursor, blink):
        val = 0x04
        if display: val |= 0x04
        if cursor: val |= 0x02
        if blink: val |= 0x01
        self.impl_write_command(0x08 | val)

    def impl_entry_mode(self, increment, shift):
        pass