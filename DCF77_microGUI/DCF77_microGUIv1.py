import hardware_setup
from gui.core.ugui import Screen, ssd
from gui.widgets import Label, LED, Dial, Pointer, Button, CloseButton, Textbox
from gui.core.writer import CWriter

# Font for CWriter
import gui.fonts.arial10 as arial10
import gui.fonts.arial35 as hours_font
import gui.fonts.freesans20 as seconds_font
import gui.fonts.freesans20 as date_font

from gui.core.colors import *
#-------------------------------
# Now import other modules
from cmath import rect, pi
import uasyncio as asyncio
import time
#-------------------------------

# DEBUG probe definitions
from debug_utility.pulses import *
# D0 = Probe(27) # LocalTimeCalendar._timer_IRQ
# D1 = Probe(16) # DCF_Decoder._DCF_clock_IRQ_handler
# D2 = Probe(17) # DCF_Decoder.frame_decoder
# D3 = Probe(18) # DCF_Display_nanoGUI.update_time_status
# D4 = Probe(19) # DCF_Display_nanoGUI.update_signal_status
# D5 = Probe(20) # DCF_Display_nanoGUI.update_date_and_time
# D6 = Probe(21) # _StatusController.time_status == SYNC
# D7 = Probe(26) # gui.core.nanogui.refresh(ssd)


# import DCF modules
TONE_GPIO = const(7) # the GPIO where DCF signal is received by MCU
from DCF77.decoder_uGUIv1 import *
from DCF77.local_time_calendar_uGUI import LocalTimeCalendar

class DCF():
    def __init__(self):
        self.local_time = LocalTimeCalendar()
        self.dcf_decoder = DCF_Decoder(TONE_GPIO, self.local_time)
        asyncio.create_task(self.dcf_decoder.DCF_signal_monitoring())
        asyncio.create_task(self.dcf_decoder.frame_decoder())
        asyncio.create_task(self.update())
        
    async def update(self):
        while True:
            D7.off()
            await Screen.timer_elapsed.wait()
            D7.on()
            Screen.timer_elapsed.clear()
            self.local_time.next_second()
    #         print( f"{self.local_time.get_local_time()}\t{self.dcf_decoder.get_time_status()}\t{self.dcf_decoder.get_signal_status()}")

        
    def localtime(self):
#         localtime : t[0]:year, t[1]:month, t[2]:mday, t[3]:hour, t[4]:minute, t[5]:second, t[6]:weekday, t[7]:time_zone
        return self.local_time.get_raw_time_and_date()
    
    def get_status(self):
        ts = self.dcf_decoder.get_time_status()
        time_state = ts[1]
        if ts[1] == SYNC:
            ts_symbol = "sync'd"
        elif time_state == SYNC_IN_PROGRESS:
            ts_symbol = "in progress"
        elif time_state == SYNC_FAILED:
            ts_symbol = "frame fail"
        elif time_state == OUT_OF_SYNC:
            ts_symbol = "out of sync"
        else:
            ts_symbol = "init"
        ss = self.dcf_decoder.get_signal_status()
        bit_rank = ss[0]
        last_bit = ss[1]
        return (ts_symbol,bit_rank,last_bit)
#         time_status = [self._status_controller.time_event, self._status_controller.time_state, self._status_controller.error_message]
#         signal_status [self._status_controller.last_received_frame_bit_rank, self._status_controller.last_received_frame_bit,
#                 self._status_controller.signal_event, self._status_controller.signal_state]
        
    def get_time_status_color(self):
        status = self.dcf_decoder.get_time_status()
        state = status[1]
        if state == SYNC:
            color = GREEN
        elif state == SYNC_IN_PROGRESS:
            color = GREY
        elif state == SYNC_FAILED:
            color = YELLOW
        elif state == OUT_OF_SYNC:
            color = RED
        else:
            color = WHITE
        return color
    
dcf_clock = DCF()


# triggering mechanism = 1-second internal timer
from machine import Timer
def timer_IRQ(timer):
    irq_state = machine.disable_irq()
    D0.on()
    Screen.timer_elapsed.set()
    D0.off()
    machine.enable_irq(irq_state)
timer = Timer(mode=Timer.PERIODIC, freq=1, callback=timer_IRQ)
# Screen._timer_elapsed = asyncio.ThreadSafeFlag() # evolution possible du Screen : prendre en compte ThreadSafeFlag
Screen.timer_elapsed = asyncio.Event() # evolution possible du Screen : prendre en compte ThreadSafeFlag

days   = ('LUN', 'MAR', 'MER', 'JEU', 'VEN', 'SAM', 'DIM')
months = ('JAN', 'FEV', 'MAR', 'AVR', 'MAY', 'JUN', 'JUL',
          'AOU', 'SEP', 'OCT', 'NOV', 'DEC')


def fwdbutton(wri, row, col, cls_screen, text='Next'):
    def fwd(button):
        Screen.change(cls_screen)  # Callback
    Button(wri, row, col, callback = fwd,
           height=10, width=35,
           fgcolor = YELLOW, bgcolor = BLACK,
           text = text, shape = RECTANGLE)


class DCF_clock_screen(Screen):
    def __init__(self):
        super().__init__()
        labels = {'bdcolor' : False,
                  'fgcolor' : YELLOW,
                  'bgcolor' : BLACK,
                  'justify' : Label.CENTRE,
          }
        # verbose default indicates if fast rendering is enabled
        wri = CWriter(ssd, arial10, YELLOW, BLACK, verbose=False)  # Report on fast mode. Or use verbose=False
        wri_date = CWriter(ssd, date_font, YELLOW, BLACK, verbose=False)  # Report on fast mode. Or use verbose=False
        wri_time = CWriter(ssd, hours_font, YELLOW, BLACK, verbose=False)  # Report on fast mode. Or use verbose=False
        wri_seconds = CWriter(ssd, seconds_font, YELLOW, BLACK, verbose=False)  # Report on fast mode. Or use verbose=False
        
        gap = 4  # Vertical gap between widgets
        fwdbutton(wri, 4, 80, DCF_detail_screen, text='> detail')
       
        self.dial = Dial(wri, 2, 2, height = 55, ticks = 12, fgcolor = GREEN, pip = GREEN)
        
        row = self.dial.mrow + gap
        self.lbl_date = Label(wri_date, row, 2, 124, **labels)
        row = self.lbl_date.mrow + gap
        self.lbl_tim = Label(wri_time, row, 2, '00:00', **labels)
        self.led_status = LED(wri, row-gap, 105, height=10, bdcolor=False , fgcolor=False )
        row += 12
        self.lbl_sec = Label(wri_seconds, row, 100, '00', **labels)
        
        # setup async coroutines
        self.reg_task(self.aclock_screen())

    async def aclock_screen(self):
        def uv(phi):
            return rect(1, phi)
        hrs = Pointer(self.dial)
        mins = Pointer(self.dial)
        secs = Pointer(self.dial)

        hstart = 0 + 0.7j  # Pointer lengths. Will rotate relative to top.
        mstart = 0 + 1j
        sstart = 0 + 1j 

        while True:
            t = dcf_clock.localtime()
            color = dcf_clock.get_time_status_color()
            # localtime : t[0]:year, t[1]:month, t[2]:mday, t[3]:hour, t[4]:minute, t[5]:second, t[6]:weekday, t[7]:time_zone
            hrs.value(hstart * uv(-t[3] * pi/6 - t[4] * pi / 360), CYAN)
            mins.value(mstart * uv(-t[4] * pi/30), CYAN)
            secs.value(sstart * uv(-t[5] * pi/30), RED)
            self.lbl_tim.value(f"{t[3]:02d}:{t[4]:02d}")
            self.lbl_sec.value(f"{t[5]:02d}")
            self.lbl_date.value(f"{days[t[6]]} {t[2]} {months[t[1] - 1]}")
            if t[5]%2==0 : self.led_status(True)
            else: self.led_status(False)
            self.led_status.color(color)
            D3.off()
            await Screen.timer_elapsed.wait()
            D3.on()
            Screen.timer_elapsed.clear()

 


class DCF_detail_screen(Screen):
    def __init__(self):
        super().__init__()
        labels = {'bdcolor' : False,
                  'fgcolor' : YELLOW,
                  'bgcolor' : DARKBLUE,
                  'justify' : Label.CENTRE,
          }

        wri = CWriter(ssd, arial10, YELLOW, BLACK, verbose=False)  # Report on fast mode. Or use verbose=False
        wri_time = CWriter(ssd, seconds_font, YELLOW, BLACK, verbose=False)  # Report on fast mode. Or use verbose=False
        gap = 4  # Vertical gap between widgets
        fwdbutton(wri, 4, 80, DCF_clock_screen, text='> clock')
        row = 22
        self.lbl_date = Label(wri, row, 2, 120, **labels)
        row = self.lbl_date.mrow + gap
        self.tb = Textbox(wri, row, 2, 120, 7) 
        self.reg_task(self.adetail_screen())

        
    async def adetail_screen(self):
        while True:
            t = dcf_clock.localtime()
            # localtime : t[0]:year, t[1]:month, t[2]:mday, t[3]:hour, t[4]:minute, t[5]:second, t[6]:weekday, t[7]:time_zone
            self.lbl_date.value(f"{days[t[6]]} {t[2]} {months[t[1] - 1]} {t[0]} {t[3]:02d}:{t[4]:02d}")
            ts_symbol,bit_rank,last_bit = dcf_clock.get_status()
            if last_bit == None:
                last_bit = "x"
            self.tb.append(f"{ts_symbol:<11s} bit[{bit_rank:02d}]={last_bit:1s} s{t[5]:02d}")

            await Screen.timer_elapsed.wait()
            Screen.timer_elapsed.clear()
    


#--------------------------------------------------

if __name__ == "__main__":
    print('main : DCF_clock_screen')
#     Screen.change(DCF_clock_screen)
    Screen.change(DCF_detail_screen)




