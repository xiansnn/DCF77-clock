import uasyncio
import ustruct, utime, machine
from machine import Timer

import micropython
micropython.alloc_emergency_exception_buf(100)

from debug_utility.pulses import Probe
D0 = Probe(27) # LocalTimeCalendar._timer_IRQ
D1 = Probe(16) # -
D2 = Probe(17) # DCF_Decoder_stub.frame_decoder
D3 = Probe(18) # DCF_Display_stub.update_time_status
D4 = Probe(19) # -
D5 = Probe(20) # DCF_Display_stub.update_date_and_time
D6 = Probe(21) # DCF_Decoder_stub._end_of_frame
D7 = Probe(26) # DCF_Display_stub.update_date_and_time   -- refresh(ssd)


class LocalTimeCalendar():
    """
The local clock/calendar, triggered by 1-second local timer.
The one-second period is adjusted by a PID servo_loop, in order to take into account the actual routine processing time.
    """
    def __init__(self, display):
        self._display = display
        # triggering mechanism = 1-second internal timer
        self.timer = Timer(mode=Timer.PERIODIC, freq=1, callback=self._timer_IRQ)
        self._timer_elapsed = uasyncio.ThreadSafeFlag()
        
        #init conversion tables
        self._month_values = ("JAN","FEV","MAR","AVR","MAI","JUN","JUL","AOU","SEP","OCT","NOV","DEC")
        self._week_day_values = ("LUN","MAR","MER","JEU","VEN","SAM","DIM")
        self._time_zone_values = (0,2,1) #time_zone = 2 => CET = +1, time_zone = 1 => CEST = +2
        
        #init local time
        self.year = 0
        self.month = "xxx"
        self.day = 0
        self.week_day = "xxx"
        self.hours = 0
        self.minutes = 0
        self.seconds = 0
        self.time_zone = 0
        
        # init display
        clock_update = (self.week_day, self.day, self.month, self.year,
                       self.hours, self.minutes, self.seconds, self.time_zone)
        self._display.update_date_and_time(clock_update)
    
    def _timer_IRQ(self, timer):
        irq_state = machine.disable_irq()
        D0.on()
        self._timer_elapsed.set()
        D0.off()
        machine.enable_irq(irq_state)

    def sync_time(self, DCF_time_pack):
        """
        When a DCF full correct frame is received, the decoder packs a set of bytes
        and this set is used to sync the local clock
        """
        (year, month, day, week_day, hours, minutes, time_zone) = ustruct.unpack("6HB",DCF_time_pack)
        self.year = 2000+year
        self.month = self._month_values[month-1]
        self.day = day
        self.week_day = self._week_day_values[week_day-1]
        self.hours = hours
        self.minutes = minutes
        self.seconds = 0
        self.time_zone = self._time_zone_values[time_zone]


    def _next_hour(self):
        if self.hours==23:
            self.hours = 0
        else:
            self.hours +=1
            
    def _next_minute(self):
        if self.minutes==59:
            self.minutes = 0
            self._next_hour()
        else:
            self.minutes +=1
            
    def start_new_minute(self):
        """ When a "next minute" signal is received, but frame is not correctly decoded, we only sync the seconds to 0"""
        self.seconds = 59

    async def next_second(self):
        """ coroutine triggered by the 1-second local timer """
        while True:
            # triggering the coroutine
            await self._timer_elapsed.wait()
            self._timer_elapsed.clear()
            
            # update time
            if self.seconds == 59:
                self.seconds = 0
                self._next_minute()
            else:
                self.seconds +=1
            self.update_display()
                
            
    def update_display(self):
        DCF_clock_update = (self.week_day, self.day, self.month, self.year,
                       self.hours, self.minutes, self.seconds, self.time_zone)
        self._display.update_date_and_time(DCF_clock_update)
        self._display.update_seconds(self.seconds)
 
            
if __name__ == "__main__":
    
    from random import randint
     
    SIGNAL_STATUS_TAB = const("")
    TIME_STATUS_TAB   = const("\t\t")
    LOCAL_TIME_TAB    = const("\t\t\t\t\t\t\t\t\t")

    class DCF_Display_stub():
        def __init__(self):
            print("init DCF_Display_stub")
            
        def update_time_status(self, event, new_status, message=""):
            D3.on()
            print(f"{TIME_STATUS_TAB}time_status\t-- ({event:^20s}) --> [{new_status:^20s}] : {message}")
            D3.off()
   
        def update_signal_status(self, current_string, event, new_status):
            D4.on()
            if current_string != None:
                data = current_string[-1]
                rank = len(current_string)-1
                print(f"{SIGNAL_STATUS_TAB}signal_status\t-- ({event:^20s}) --> [{new_status:^20s}] : Data[{rank:0>2d}] = {data}")
            else:
                print(f"{SIGNAL_STATUS_TAB}signal_status\t-- ({event:^20s}) --> [{new_status:^20s}] : No Data")
            D4.off()
                
        def update_date_and_time(self, clock_update):
            D5.on()
            week_day , day, month, year, hours, minutes, seconds, time_zone = clock_update
            print(f"{LOCAL_TIME_TAB}LocalTime:\t{week_day} {day} {month} {year:0>2d}\t{hours:0>2d}:{minutes:0>2d}:{seconds:0>2d}\tgmt{time_zone:<+3d}")
            D5.off()
            D7.on()
            #refresh()
            D7.off()
            
        def update_seconds(self, seconds):
            pass
            
    class DCF_decoder_stub():
        def __init__(self,local_clock_calendar, display):
            print("init DCF_decoder_stub")
            self._local_time = local_clock_calendar
            self.display = display
            self.time_zone_num = randint(1,2)
            self.minutes = randint(1,59)
            self.hours = randint(0,23)
            self.month = randint(1,12)
            self.day = randint(1,31)
            self.week_day_num = randint(1,7)
            self.year = randint(20,30)
             
        def _change_calendar(self):
            self.time_zone_num = randint(1,2)
            self.minutes = randint(1,59)
            self.hours = randint(0,23)
            self.day = randint(1,31)
            self.month = randint(1,12)
            self.week_day_num = randint(1,7)
            self.year = randint(20,30)
            self.display.update_time_status("CHANGE CALENDAR", "SYNC")
            
        async def frame_decoder(self):
            while True:
                D2.off()
                await uasyncio.sleep(randint(20,30))
                D2.on()
                print("Frame sync")
                self._change_calendar()
                self._local_time.sync_time(ustruct.pack("6HB",
                     self.year, self.month, self.day, self.week_day_num, self.hours, self.minutes, self.time_zone_num))
        async def _end_of_frame(self):
            while True:
                D6.off()
                await uasyncio.sleep(randint(15,25))
                D6.on()
                print("EoF")
                self._local_time.start_new_minute()
                
 
            
    
    

    ################### test ############################ 
    # init main tasks
    display = DCF_Display_stub()
    local_clock_calendar = LocalTimeCalendar(display)
    DCF_decoder = DCF_decoder_stub(local_clock_calendar, display)

    # local time setup coroutines
    local_time_coroutine = local_clock_calendar.next_second()

    # DCF decoder setup coroutines      
    DCF_frame_coroutine = DCF_decoder.frame_decoder()
    DCF_EoF_coroutine = DCF_decoder._end_of_frame()

    #start coroutines
    scheduler = uasyncio.get_event_loop()
    
    scheduler.create_task(local_time_coroutine)
    
    scheduler.create_task(DCF_frame_coroutine)
    scheduler.create_task(DCF_EoF_coroutine)
    
    scheduler.run_forever()
