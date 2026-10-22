# DSP & Mathematical Specification

## 1. Signal Standardization & Resampling

### Sample Rate & Channel Downmix
- **Input**: WASAPI shared-mode stream at $f_{\text{in}} = 48,000\text{ Hz}$, 32-bit IEEE float, stereo.
- **Downmix**:
  $$x_{\text{mono}}[n] = \frac{x_{\text{left}}[n] + x_{\text{right}}[n]}{2}$$
- **Anti-Aliasing Filter & Decimation**:
  - The upper frequency of interest is $f_{\max} = 5,000\text{ Hz}$.
  - Canonical target sample rate: $f_s = 11,025\text{ Hz}$ (Nyquist limit $5,512.5\text{ Hz}$).
  - A polyphase Kaiser-windowed sinc filter low-passes the stream with a sharp cutoff at $5,000\text{ Hz}$ before decimation to prevent high-frequency aliasing folding into musical bands.

### RMS Silence Gate
$$\text{RMS} = \sqrt{\frac{1}{N} \sum_{n=0}^{N-1} x[n]^2}$$
$$\text{dBFS} = 20 \log_{10}(\text{RMS} + 10^{-12})$$
If $\text{dBFS} < -50$, the buffer is dropped immediately without performing STFT or landmark extraction.

---

## 2. Spectrogram & Peak Picking

### Short-Time Fourier Transform (STFT)
- **Window**: Periodic Hanning window of length $N_{\text{fft}} = 2048$ samples ($\approx 185.8\text{ ms}$).
- **Hop Size**: $H = 256$ samples ($\approx 23.2\text{ ms}$, $87.5\%$ temporal overlap).
- **Frequency Resolution**:
  $$\Delta f = \frac{f_s}{N_{\text{fft}}} = \frac{11025}{2048} \approx 5.3833\text{ Hz/bin}$$
- **Monitored Range**: Bins $5$ to $928$ ($\approx 26.9\text{ Hz}$ to $4,995.7\text{ Hz}$).
- **Log Power Spectrogram**:
  $$M_{\text{dB}}(f, t) = 20 \log_{10}(|X(f, t)| + 10^{-10})$$

### Dynamic Spectral Floor
$$M_{\max} = \max_{f \in [5, 928], t} M_{\text{dB}}(f, t)$$
$$\text{Threshold} = M_{\max} - 45.0\text{ dB}$$
Any time-frequency bin where $M_{\text{dB}}(f, t) < \text{Threshold}$ is masked to $-\infty$.

### 5-Band Logarithmic Division
Frequency bins are divided into 5 perceptually spaced bands to guarantee feature density across the musical spectrum:
- **Band 0 (Sub-bass)**: Bins $5\text{–}24$ ($26.9\text{–}129.2\text{ Hz}$)
- **Band 1 (Bass)**: Bins $25\text{–}59$ ($134.6\text{–}317.6\text{ Hz}$)
- **Band 2 (Midrange)**: Bins $60\text{–}139$ ($323.0\text{–}748.3\text{ Hz}$)
- **Band 3 (High-mid)**: Bins $140\text{–}349$ ($753.7\text{–}1878.8\text{ Hz}$)
- **Band 4 (Treble)**: Bins $350\text{–}928$ ($1884.2\text{–}4995.7\text{ Hz}$)

### 2D Local Maxima Filter
A point $(f_0, t_0)$ is a candidate peak if:
$$M_{\text{dB}}(f_0, t_0) \ge M_{\text{dB}}(f, t) \quad \forall (f, t) \in [f_0 - 5, f_0 + 5] \times [t_0 - 5, t_0 + 5]$$
Enforce a strict quota of at most top 1 peak per band per frame, guaranteeing temporal spacing of at least 6 frames between peaks within the same band.

---

## 3. Combinatorial Landmark Pairing & Bit Packing

### Target Zone Constraints
For each anchor peak $(f_1, t_1)$, evaluate target peaks $(f_2, t_2)$ satisfying:
1. $\Delta t = t_2 - t_1 \in [3, 258]$ frames ($0.07\text{ s}$ to $5.98\text{ s}$).
2. $|f_2 - f_1| \le 250$ bins ($\Delta f \le 1,345.8\text{ Hz}$).
3. Rank all candidate target peaks by magnitude $A_2 = M_{\text{dB}}(f_2, t_2)$ descending; select the top $N = 5$ peaks.

### 32-Bit Bit-Packing Layout
To preserve strict invariance against equalization and MP3 compression, amplitude is excluded from the hash.

| Field | Bit Range | Size (Bits) | Valid Range | Description |
| :--- | :--- | :--- | :--- | :--- |
| $f_1$ | 22..31 | 10 | $0\text{–}1023$ | Anchor frequency bin |
| $f_2$ | 12..21 | 10 | $0\text{–}1023$ | Target frequency bin |
| $\Delta t_{\text{packed}}$ | 4..11 | 8 | $0\text{–}255$ | Frame delta $(t_2 - t_1) - 3$ |
| Reserved | 0..3 | 4 | $0$ | Reserved (set to 0) |

$$\text{Hash}_{\text{u32}} = ((f_1 \ \& \ \text{0x3FF}) \ll 22) \mid ((f_2 \ \& \ \text{0x3FF}) \ll 12) \mid (((\Delta t - 3) \ \& \ \text{0xFF}) \ll 4)$$

### PostgreSQL Two's Complement Bit-Cast
$$\text{Hash}_{\text{i32}} = \begin{cases} \text{Hash}_{\text{u32}} - 2^{32} & \text{if } \text{Hash}_{\text{u32}} \ge 2^{31} \\ \text{Hash}_{\text{u32}} & \text{otherwise} \end{cases}$$

---

## 4. Matching & In-Track Prominence Scoring

### Offset Difference & Histogram
Given query landmarks $[(h_k, t_{k,\text{query}})]$, the database returns postings $[(s_i, t_{i,\text{track}})]$.
Compute relative time offsets:
$$\delta t = t_{i,\text{track}} - t_{k,\text{query}}$$
Accumulate exact integer occurrences in $H[s][\delta t]$.

### Sliding Window Smoothing
To prevent boundary artifacts caused by fractional STFT frame alignment, evaluate candidate offsets using a 3-frame sliding window sum:
$$\text{Score}(s, t) = H[s][t - 1] + H[s][t] + H[s][t + 1]$$

### In-Track Prominence Condition
Let candidate track $s^*$ have highest peak score $V_1(s^*) = \max_t \text{Score}(s^*, t)$ at offset $t^*$.
Define within-track noise floor:
$$V_{\text{noise}}(s^*) = \max_{t \notin [t^* - 10, t^* + 10]} \text{Score}(s^*, t)$$
The match is accepted as genuine if and only if:
1. $V_1(s^*) \ge 15$
2. $\frac{V_1(s^*)}{\max(V_{\text{noise}}(s^*), 1)} \ge 3.0$

If a runner-up song $s'$ achieves $V_1(s') \ge 15$, verify duplicate identity (e.g. remastered album editions) by measuring matching hash overlap:
$$\text{Overlap}(s^*, s') = \frac{|\text{Hashes}(s^*) \cap \text{Hashes}(s')|}{\min(|\text{Hashes}(s^*)|, |\text{Hashes}(s')|)}$$
If $\text{Overlap} \ge 0.70$, $s^*$ is confirmed and $s'$ is marked as an acoustic duplicate.
