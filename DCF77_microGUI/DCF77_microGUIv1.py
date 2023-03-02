import hardware_setup
from gui.core.ugui import Screen, ssd
from gui.widgets import Label, LED, Dial, Pointer, Button, Textbox
from gui.core.writer import CWriter
# Font for CWriter
import gui.fonts.arial10 as arial10
import gui.fonts.arial35 as hours_font
import gui.fonts.freesans20 as seconds_font
import gui.fonts.freesans20 as date_font
from gui.core.colors import *
#------------------------------------------------------------------------------
# Now import other modules
from cmath import rect, pi
import uasyncio as asyncio
import time

#------------------------------------------------------------------------------
# DEBUG logic analyser probe definitions
from debug_utility.pulses import *
# D0 = Probe(27) # one_second_coroutine or DHT11 pulses train
# D1 = Probe(16) # DCF_Decoder._DCF_clock_IRQ_handler
# D2 = Probe(17) # DCF_Decoder.frame_decoder
# D3 = Probe(18) # DCF_clock_screen.aclock_screen
# D4 = Probe(19) # _StatusController.signal_received
# D5 = Probe(20) # _StatusController.signal_timeout
# D6 = Probe(21) # time_status == SYNC
# D7 = Probe(26) # -


#------------------------------------------------------------------------------
# triggering mechanism = one-second internal timer
from machine import Timer

def one_second_timer_IRQ(timer):
    irq_state = machine.disable_irq()
    asyncio.timer_elapsed.set()
    machine.enable_irq(irq_state)

timer = Timer(mode=Timer.PERIODIC, freq=1, callback=one_second_timer_IRQ)

asyncio.timer_elapsed = asyncio.Event() # evolution possible du Screen : prendre en compte ThreadSafeFlag

# define coroutine that executes each second
async def one_second_coroutine():
    while True:
        D0.off()
        await asyncio.timer_elapsed.wait()
        D0.on()
        asyncio.timer_elapsed.clear()
        dcf_clock.next_second()

asyncio.create_task(one_second_coroutine())


#------------------------------------------------------------------------------
# import and setup temperature and humidity device
from lib_pico.dht_v1 import DHT11device
DHT_PIN_IN = const(9)
PERIOD = const(50)
dht11_device = DHT11device(DHT_PIN_IN, PERIOD)
asyncio.create_task(dht11_device.async_measure())



#------------------------------------------------------------------------------
# import DCF modules
from DCF77.DCF77_device import DCF_device
TONE_GPIO = const(7) # the GPIO where DCF signal is received by MCU
dcf_clock = DCF_device(TONE_GPIO)
asyncio.create_task(dcf_clock.dcf_decoder.DCF_signal_monitoring())
asyncio.create_task(dcf_clock.dcf_decoder.frame_decoder())


#-------------------------- DCF77 GUI --------------------------------------
# conversions table for Calendar
days   = ('LUN', 'MAR', 'MER', 'JEU', 'VEN', 'SAM', 'DIM')
months = ('JAN', 'FEV', 'MAR', 'AVR', 'MAY', 'JUN', 'JUL', 'AOU', 'SEP', 'OCT', 'NOV', 'DEC')

def fwdbutton(wri, row, col, cls_screen, text='Next'):
    def fwd(button):
        Screen.change(cls_screen)  # Callback
    Button(wri, row, col, callback = fwd,
           height=10, width=35,
           fgcolor = YELLOW, bgcolor = BLACK,
           text = text, shape = RECTANGLE)
    
from DCF77.decoder_uGUIv1 import *   
def time_status_rendering(dcf_device):
    status = dcf_device.dcf_decoder.get_time_status()
    state = status[1]
    if state == SYNC:
        blink = False
        color = GREEN
    elif state == SYNC_IN_PROGRESS:
        blink = True
        color = GREY
    elif state == SYNC_FAILED:
        blink = True
        color = YELLOW
    elif state == OUT_OF_SYNC:
        blink = False
        color = RED
    else:
        blink = True
        color = WHITE
    return (blink, color)

#------------------------------------------------------------------------------
class DCF_clock_screen(Screen):
    def __init__(self):
        super().__init__()
        labels = {'bdcolor' : False,
                  'fgcolor' : YELLOW,
                  'bgcolor' : BLACK,
                  'justify' : Label.CENTRE,
          }
        temp_colors = {'bdcolor' : False,
                  'fgcolor' : WHITE,
                  'bgcolor' : BLACK,
                  'justify' : Label.CENTRE,
          }
        # verbose default indicates if fast rendering is enabled
        wri         = CWriter(ssd, arial10, YELLOW, BLACK, verbose=False)  
        wri_date    = CWriter(ssd, date_font, YELLOW, BLACK, verbose=False)  
        wri_time    = CWriter(ssd, hours_font, YELLOW, BLACK, verbose=False)  
        wri_seconds = CWriter(ssd, seconds_font, YELLOW, BLACK, verbose=False)  
        wri_temp    = CWriter(ssd, seconds_font, YELLOW, BLACK, verbose=False)  
        
        gap = 4  # Vertical gap between widgets
        fwdbutton(wri, 4, 80, DCF_detail_screen, text='> detail')
       
        self.dial = Dial(wri, 2, 2, height = 55, ticks = 12, fgcolor = GREEN, pip = GREEN)
        
        col1 = 2 + self.dial.mcol + 3*gap
        self.lbl_temperature = Label(wri_temp, 20, col1, 30, **temp_colors)
        col2 = self.lbl_temperature.mcol
        self.lbl_temp_unit = Label(wri, 20, col2, "c", **temp_colors)
        row = self.lbl_temperature.mrow
        self.lbl_humidity = Label(wri_temp, row, col1, 30, **temp_colors)
        self.lbl_hum_unit = Label(wri, row, col2, "%", **temp_colors)
        
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
            temperature  = dht11_device.get_temperature()
            humidity = dht11_device.get_humidity()
            self.lbl_temperature.value(f"{temperature:3.0f}")
            self.lbl_humidity.value(f"{humidity:3.0f}")
            t = dcf_clock.get_local_time()
            blink, color = time_status_rendering(dcf_clock)
            # Format
            ## localtime : t[0]:year, t[1]:month, t[2]:mday, t[3]:hour, t[4]:minute, t[5]:second, t[6]:weekday, t[7]:time_zone
            hrs.value(hstart * uv(-t[3] * pi/6 - t[4] * pi / 360), CYAN)
            mins.value(mstart * uv(-t[4] * pi/30), CYAN)
            secs.value(sstart * uv(-t[5] * pi/30), RED)
            self.lbl_tim.value(f"{t[3]:02d}:{t[4]:02d}")
            self.lbl_sec.value(f"{t[5]:02d}")
            self.lbl_date.value(f"{days[t[6]-1]} {t[2]} {months[t[1]-1]}")
            if blink == True:
                if t[5]%2==0 : self.led_status(True)
                else: self.led_status(False)
                self.led_status.color(color)
            else:
                self.led_status(True)
                self.led_status.color(color)
            D3.off()
            await asyncio.timer_elapsed.wait()
            D3.on()
            asyncio.timer_elapsed.clear()
            
            
#------------------------------------------------------------------------------
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
            t = dcf_clock.get_local_time()
            # localtime : t[0]:year, t[1]:month, t[2]:mday, t[3]:hour, t[4]:minute, t[5]:second, t[6]:weekday, t[7]:time_zone
            self.lbl_date.value(f"{days[t[6]-1]} {t[2]} {months[t[1]-1]} {t[0]} {t[3]:02d}:{t[4]:02d}")
            ts_symbol,bit_rank,last_bit = dcf_clock.get_status()
            if last_bit == None:
                last_bit = "x"
            self.tb.append(f"{ts_symbol:<11s} bit[{bit_rank:02d}]: {last_bit:1s} s{t[5]:02d}")

            await asyncio.timer_elapsed.wait()
            asyncio.timer_elapsed.clear()
    


#----------------- main program --------------------------

if __name__ == "__main__":
    print('main program')
    Screen.change(DCF_clock_screen)
#     Screen.change(DCF_detail_screen)




