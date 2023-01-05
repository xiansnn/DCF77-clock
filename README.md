# DCF77
 A project that decodes radio signal from DCF77 station

The project uses lib_pico and debug_utility from https://github.com/xiansnn/RP2-micropython

In this version, the radio signal is received via a WebSDR (http://www.websdr.org/) and in particular the one from University of Twente in Enshede The Netherland (http://websdr.ewi.utwente.nl:8901/)

As a result, there is no direct reception of the radio siganl. The radio signal is converted in audio signal by the WebSDR, then the audio signal is captured by a microphone (HW-484 or KY-038) and processed by a special circuitry to get a logical 3.3V level synchronized with the radio signal
