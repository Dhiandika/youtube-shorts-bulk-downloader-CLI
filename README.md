<div align='center'>

<h1>Download all YouTube Shorts from a channel. Bulk download all shorts from a specified YouTube channel using Python 3.10.0 and above  </h1>
<h4>


</div>

# :notebook_with_decorative_cover: Table of Contents

- [About the Project](#star2-about-the-project)
- [Contributing](#wave-contributing)


## :star2: About the Project
--- 
Fitur yang Tersedia dalam Kode:
- Mengambil daftar video Shorts dari suatu channel YouTube.
- Mendukung pembatasan jumlah video yang diambil.
- Mengunduh video Shorts dengan opsi kualitas yang bisa dipilih.
- Menyimpan file dengan nama sesuai judul video + penomoran.
- Menyimpan caption (deskripsi video) dalam file teks.
- Menggunakan multithreading untuk mempercepat proses unduhan.
- Menerapkan retry otomatis jika terjadi kegagalan.
- Menampilkan progress unduhan menggunakan tqdm.
- Menghapus file duplikat untuk menghindari penyimpanan ganda.
- Menampilkan ringkasan hasil unduhan.

---

### :performing_arts: Fitur Pembuatan Caption Otomatis (`caption.py`)

Skrip `caption.py` dirancang untuk secara otomatis menghasilkan caption yang menarik untuk konten media sosial, khususnya yang berfokus pada talenta Hololive. Berikut adalah kemampuan utamanya:

- **Input Fleksibel**: Membaca semua file `.txt` yang tersimpan di dalam folder `downloads_cut`. Setiap file teks ini akan dijadikan dasar prompt untuk pembuatan caption.
- **Integrasi AI Gemini**: Menggunakan model AI generatif dari Google (Gemini Pro) untuk membuat narasi caption. Pengguna akan diminta untuk memasukkan kunci API Gemini mereka langsung melalui terminal saat skrip dijalankan.
- **Kunci API Gemini**: Kunci API yang diperlukan untuk menjalankan skrip ini dapat diperoleh secara gratis melalui [Google AI Studio](https://aistudio.google.com/app/apikey).
- **Prompting Terstruktur**: Mengirimkan prompt ke model AI dengan instruksi sistem yang detail dan contoh *one-shot* untuk memastikan caption yang dihasilkan sesuai dengan format yang diinginkan, termasuk:
    - Deskripsi singkat talenta.
    - Fakta menarik atau detail unik mengenai talenta.
    - Penyebutan sumber klip (jika relevan dari prompt input).
    - Kumpulan 15-25 hashtag yang relevan.
- **Output Langsung**: Setelah caption berhasil dibuat, skrip akan **menulis ulang (overwrite)** konten file `.txt` asli dengan caption yang baru. Ini berarti konten prompt awal dalam file tersebut akan digantikan oleh caption yang telah diproses oleh AI.
- **Penggunaan**: Cukup jalankan `python caption.py` dari terminal, masukkan kunci API Gemini Anda ketika diminta, dan skrip akan memproses semua file teks di folder `downloads_cut`.

**Penting**: Karena skrip ini menimpa file asli, disarankan untuk membuat cadangan dari file-file di `downloads_cut` jika konten prompt awal masih ingin Anda simpan.
---

### :camera: Screenshots
<div align="center"> <a href=""><img src="/images/1.png" alt='image' width='800'/></a> </div>
<div align="center"> <a href=""><img src="/images/image.png" alt='image' width='800'/></a> </div>

---

## :toolbox: Getting Started

### :gear: Installation

- install libraries
```bash
pip install requirements.txt
```
- Run
```bash 
  python main.py
  ```

