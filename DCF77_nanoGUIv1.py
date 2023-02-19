# Initialise hardware and framebuf before importing modules.
from color_setup import ssd  # Create a display instance
from gui.core.nanogui import refresh  # Color LUT is updated now.
from gui.widgets.label import Label
from gui.widgets.dial import Dial, Pointer
from gui.widgets.textbox import Textbox
from gui.widgets.led import LED
# Now import other modules
import cmath
import utime
from gui.core.writer import CWriter

# Font for CWriter
import gui.fonts.arial10 as arial10
import gui.fonts.arial35 as hours_font
import gui.fonts.freesans20 as seconds_font
import gui.fonts.freesans20 as date_font
import gui.fonts.arial10 as frame_font

from gui.core.colors import *

from debug_utility.pulses import Probe
D0 = Probe(26) # LocalTimeCalendar._timer_IRQ
D1 = Probe(16) # DCF_Decoder._DCF_clock_IRQ_handler
D2 = Probe(17) # DCF_Decoder.frame_decoder
D3 = Probe(18) # DCF_Display_nanoGUI.update_time_status
D4 = Probe(19) # DCF_Display_nanoGUI.update_signal_status
D5 = Probe(20) # DCF_Display_nanoGUI.update_date_and_time
D6 = Probe(21) # _StatusController.time_status == SYNC
D7 = Probe(22) # gui.core.nanogui.refresh(ssd)


class DCF_Display_nanoGUI():
    def __init__(self):
        refresh(ssd, True)  # Initialise and clear display.
        self.uv = lambda phi : cmath.rect(1, phi)  # Return a unit vector of phase phi
        self.pi = cmath.pi
        
        year = 2000
        month = 1 # in (1 ... 12)
        mday = 1 # in (1 ... 31)
        hour = 0 # in (0 ... 23)
        minute = 0 # in (0 ... 59)
        second = 0 # in (0 ... 59)
        weekday = 0 # in (0 ... 6) (LUN ... DIM)
        yearday = 1 # in (1 ... 366)
        time_zone = 0
        self._local_time = [year, month, mday, hour, minute, second, weekday, yearday, time_zone]        
        self._status = ["x", BLACK] # time status symbol, time status color
        
        # Instantiate CWriter
        CWriter.set_textpos(ssd, 0, 0)  # In case previous tests have altered it
        self.wri = CWriter(ssd, arial10, YELLOW, BLACK, verbose=False)  # Report on fast mode. Or use verbose=False
        self.wri.set_clip(True, True, False)
        self.wri_date = CWriter(ssd, date_font, YELLOW, BLACK, verbose=False)  # Report on fast mode. Or use verbose=False
        self.wri_date.set_clip(True, True, False)
        self.wri_hours = CWriter(ssd, hours_font, YELLOW, BLACK, verbose=False)  # Report on fast mode. Or use verbose=False
        self.wri_hours.set_clip(True, True, False)
        self.wri_seconds = CWriter(ssd, seconds_font, YELLOW, BLACK, verbose=False)  # Report on fast mode. Or use verbose=False
        self.wri_seconds.set_clip(True, True, False)
        self.wri_text_frame = CWriter(ssd, frame_font, GREY, BLACK, verbose=False)  # Report on fast mode. Or use verbose=False
        self.wri_text_frame.set_clip(True, True, True)
 
        # Instantiate displayable objects
        self.dial = Dial(self.wri, 2, 2, height = 65, ticks = 12, bdcolor=False, label=None, pip=False)  # Border in fg color
        self.hrs = Pointer(self.dial)
        self.mins = Pointer(self.dial)
        self.secs = Pointer(self.dial)
        
        self.lbl_date = Label(self.wri_date, 70, 2, 125)
        self.lbl_hours = Label(self.wri_hours, 90, 2, 100)
        self.lbl_seconds = Label(self.wri_seconds, 100, 100, 10)
        self.lbl_time_zone= Label(self.wri,2, 85, 2)
        self.led_status = LED(self.wri, 2, 70, height=8, bdcolor=BLACK)
        self.frame = Textbox(self.wri_text_frame, 15, 110, 6, 5, clip=False)

        self.hstart = 0 + 0.7j  # Pointer lengths and position at top
        self.mstart = 0 + 0.92j
        self.sstart = 0 + 0.92j 
               
    def update_time_status(self, event, new_status, message=""):
        D3.on()
        if new_status == TIME_INIT:
            self._status[0] = "-"
            self._status[1] = WHITE
        elif new_status == OUT_OF_SYNC:
            self._status[0] = "X"
            self._status[1] = RED
        elif new_status == SYNC_IN_PROGRESS:
            self._status[0] = ">"
            self._status[1] = WHITE
        elif new_status == SYNC_FAILED:
            self._status[0] = "!"
            self._status[1] = YELLOW
        elif new_status == SYNC:
            self._status[0] = "#"
            self._status[1] = GREEN
        D3.off()
            
    def update_signal_status(self, current_frame, event, new_status):
        D4.on()
        if current_frame != None:
            self.frame.append(current_frame[-1], ntrim=6)
        else:
#             self.frame.append("X", ntrim=6)
            self.frame.clear()
        D4.off()

    def update_date_and_time(self, DCF_clock_update):
        D5.on()
        week_day , mday, month, year, hours, minutes, seconds, time_zone = DCF_clock_update
        self._local_time = [year, month, mday, hours, minutes, seconds, week_day, time_zone]
        t = self._local_time
        t[5] = seconds
        self.hrs.value(self.hstart * self.uv(-t[3]*self.pi/6 - t[4]*self.pi/360), YELLOW)
        self.mins.value(self.mstart * self.uv(-t[4] * self.pi/30), YELLOW)
        self.secs.value(self.sstart * self.uv(-t[5] * self.pi/30), RED)
        
        self.lbl_date.value(f"{t[6]} {t[2]} {t[1]}")
        self.lbl_hours.value(f'{t[3]:02d}:{t[4]:02d}')
        self.lbl_seconds.value(f'{t[5]:02d}')
        self.lbl_time_zone.value(f'GMT {t[7]:>+2d}')
#         self.lbl_status.value(f' {self._status[0]}',fgcolor=self._status[1],bgcolor=BLACK, bdcolor=self._status[1])
        self.led_status.color(self._status[1])
        D5.off()
        D7.on()
        refresh(ssd)
        D7.off()
        
    def update_seconds(self, seconds):
        pass
        




################### test nanoGUI ############################
        
if __name__ == "__main__":
    import uasyncio
    from DCF77.DCF77_decoder import *
    from DCF77.local_time_calendar_IRQ import LocalTimeCalendar
    TONE_GPIO = const(7)
          
    # init main tasks
    display = DCF_Display_nanoGUI()
    local_clock_calendar = LocalTimeCalendar(display)
    DCF_decoder = DCF_Decoder(TONE_GPIO, local_clock_calendar, display)

    # setup coroutines
    DCF_frame_coroutine = DCF_decoder.frame_decoder()    
    DCF_signal_monitor_coroutine = DCF_decoder.DCF_signal_monitoring()
    local_time_coroutine = local_clock_calendar.next_second()

    #start coroutines
    scheduler = uasyncio.get_event_loop()

    scheduler.create_task(local_time_coroutine)
    scheduler.create_task(DCF_signal_monitor_coroutine)
    scheduler.create_task(DCF_frame_coroutine)

    scheduler.run_forever()
    ############""
