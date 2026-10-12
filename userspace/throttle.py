import sys, time
# 標準入力を RATE バイト/秒 に抑えて標準出力へ流す
rate = int(sys.argv[1]); chunk = 8192; t0 = time.time(); sent = 0
while True:
    b = sys.stdin.buffer.read(chunk)
    if not b:
        break
    sys.stdout.buffer.write(b); sys.stdout.buffer.flush()
    sent += len(b)
    ahead = sent / rate - (time.time() - t0)
    if ahead > 0:
        time.sleep(ahead)
sys.stderr.write('sent %d bytes in %.1f s\n' % (sent, time.time() - t0))
