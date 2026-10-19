"""Optional prebuilt FIR accelerator; the SciPy path remains the fallback."""
import ctypes
from pathlib import Path
import numpy as np


class NativePhase:
    def __init__(self):
        self.library = ctypes.CDLL(str(Path(__file__).with_name('libble_fir.so')))
        self.run = self.library.ble_positive_phase
        self.run.argtypes = [np.ctypeslib.ndpointer(dtype=np.float32, ndim=1, flags='C_CONTIGUOUS'),
                             np.ctypeslib.ndpointer(dtype=np.uint8, ndim=1, flags='C_CONTIGUOUS'),
                             ctypes.c_size_t]
        self.run.restype = None

    def decide(self, values):
        values = np.ascontiguousarray(values, dtype=np.complex64)
        out = np.empty(len(values), dtype=np.uint8)
        self.run(values.view(np.float32), out, len(values))
        return out.view(np.bool_)


class NativeFir:
    def __init__(self, taps):
        self.library = ctypes.CDLL(str(Path(__file__).with_name('libble_fir.so')))
        array = np.ctypeslib.ndpointer(dtype=np.float32, ndim=1, flags='C_CONTIGUOUS')
        self.run = self.library.ble_fir
        self.run.argtypes = [array, array, ctypes.c_size_t, array, ctypes.c_size_t]
        self.run.restype = None
        self.taps = np.ascontiguousarray(taps, dtype=np.float32)
        if len(self.taps) < 2:
            raise ValueError('FIR requires at least two taps')
        self.history = np.zeros(len(self.taps) - 1, dtype=np.complex64)

    def reset(self):
        self.history.fill(0)

    def feed(self, samples):
        samples = np.ascontiguousarray(samples, dtype=np.complex64)
        if samples.ndim != 1:
            raise ValueError('Expected one-dimensional IQ')
        joined = np.concatenate((self.history, samples))
        output = np.empty(len(samples), dtype=np.complex64)
        self.run(joined.view(np.float32), self.taps, len(self.taps),
                 output.view(np.float32), len(samples))
        self.history = joined[-len(self.history):].copy()
        return output


class NativeAccessMatcher:
    def __init__(self, pattern):
        self.library = ctypes.CDLL(str(Path(__file__).with_name('libble_fir.so')))
        self.run = self.library.ble_access_hits
        self.run.argtypes = [np.ctypeslib.ndpointer(dtype=np.uint8, ndim=1, flags='C_CONTIGUOUS'),
                             ctypes.c_size_t, ctypes.c_size_t, ctypes.c_uint32,
                             np.ctypeslib.ndpointer(dtype=np.uintp, ndim=1, flags='C_CONTIGUOUS')]
        self.run.restype = ctypes.c_size_t
        if len(pattern) != 32:
            raise ValueError('Expected a 32-bit access address')
        self.pattern = int(''.join(str(int(bit)) for bit in pattern), 2)
        try:
            self.fractional = self.library.ble_access_hits_225
            self.fractional.argtypes = [self.run.argtypes[0], ctypes.c_size_t,
                                       ctypes.c_uint32, self.run.argtypes[-1]]
            self.fractional.restype = ctypes.c_size_t
        except AttributeError:
            pass

    def find_fractional(self, positive):
        positive = np.ascontiguousarray(positive, dtype=np.uint8)
        hits = np.empty(len(positive), dtype=np.uintp)
        count = self.fractional(positive, len(positive), self.pattern, hits)
        return hits[:count].tolist()


    def find(self, positive, sps):
        if sps < 1:
            raise ValueError('sps must be positive')
        positive = np.ascontiguousarray(positive, dtype=np.uint8)
        if positive.ndim != 1:
            raise ValueError('Expected one-dimensional decisions')
        hits = np.empty(len(positive), dtype=np.uintp)
        count = self.run(positive, len(positive), sps, self.pattern, hits)
        return hits[:count].tolist()
