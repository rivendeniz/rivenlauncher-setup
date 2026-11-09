RIVEN MESAJ SUNUCUSU
====================
Launcher'lar birbirine dogrudan baglanamaz; mesajlar bu kucuk sunucu uzerinden gecer.
Sunucuyu SADECE BIR KISI calistirir (sen ya da bir arkadasin). Digerleri launcher'da
Mesajlar sayfasina sunucunun adresini ve sifreyi girer.

1) Sunucuyu baslat
   - Windows: Sunucu_Baslat.bat dosyasina cift tikla, bir sifre yaz.
   - Elle:    python riven_chat_server.py --port 8780 --password SIFRE
   Ek paket gerekmez, sadece Python 3.9+ yeterli.
   Mesajlar chat_data.json dosyasinda tutulur (30 gun sonra silinir).

2) Arkadaslarin nasil baglanacak?
   a) Ayni ev/ag (LAN):  http://SUNUCU_PC_IPV4:8780   (ipconfig ile IPv4 adresi)
   b) Internet uzerinden, kolay yol - Cloudflare Tunnel (ucretsiz, port acmak gerekmez):
        cloudflared tunnel --url http://localhost:8780
      Verdigi https://....trycloudflare.com adresini herkes launcher'a girer.
   c) Internet uzerinden, VPS: sunucuyu bir VPS'te calistir, 8780 portunu ac
      (mumkunse Caddy/Nginx ile HTTPS arkasina koy).
   d) Hamachi / ZeroTier / Radmin VPN gibi sanal aglar da calisir.

3) Launcher tarafinda
   Mesajlar (sol menu) -> sunucu adresi + sifre -> Bagla.
   Mesaj atmak icin karsidaki kisiyi Hesap sayfasindan arkadas olarak eklemis olman gerekir.
   Premium da korsan da (cevrimdisi ad) olur. Isimler sunucuda ilk gelene verilir.

Guvenlik
   - Sifre koy; sifreyi yalnizca arkadaslarinla paylas.
   - HTTP kullaniyorsan mesajlar ve sifre sifrelenmeden gider; internete aciyorsan HTTPS (b veya c) kullan.
   - Korsan hesaplarda kimlik dogrulama yoktur: sunucu, bir ismi ilk kaydeden launcher'a gizli bir
     anahtar verir. O anahtar olmadan o isim adina kimse mesaj yazamaz/okuyamaz.
     Sunucudaki chat_data.json icinden bir kullanicinin kaydini silersen isim yeniden alinabilir.
