import numpy as np
import librosa
import time

X = np.random.randn(1, 3000)
Y = np.random.randn(1, 1800)

print("Starting librosa DTW...")
start = time.time()
D, wp = librosa.sequence.dtw(X, Y, metric='cityblock', global_constraints=True, band_rad=0.5)
end = time.time()
print(f"librosa took {end - start:.2f} seconds.")

try:
    from fastdtw import fastdtw
    print("Starting fastdtw...")
    start = time.time()
    dist, wp2 = fastdtw(X[0], Y[0], radius=100, dist=lambda a,b: abs(a-b))
    end = time.time()
    print(f"fastdtw took {end - start:.2f} seconds.")
except Exception as e:
    print("fastdtw failed:", e)
