import socket

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.sendto(b"Grapes are small, sweet fruits that grow in clusters on vines.", ("192.168.1.76", 5055))
