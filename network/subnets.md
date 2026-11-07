# Subnet allocation for 10.20.0.0/16 (largest requirement first, smallest prefix that fits)

Usable hosts = 2^(32-prefix) - 2.

| Subnet | Hosts needed | Prefix | Network | Usable range | Broadcast | Usable hosts |
|---|---|---|---|---|---|---|
| app | 1,000 | /22 | 10.20.0.0 | 10.20.0.1 - 10.20.3.254 | 10.20.3.255 | 1,022 |
| public | 250 | /24 | 10.20.4.0 | 10.20.4.1 - 10.20.4.254 | 10.20.4.255 | 254 |
| data | 100 | /25 | 10.20.5.0 | 10.20.5.1 - 10.20.5.126 | 10.20.5.127 | 126 |
| management | 20 | /27 | 10.20.5.128 | 10.20.5.129 - 10.20.5.158 | 10.20.5.159 | 30 |

## Working
- app: 2^9-2 = 510 < 1000, 2^10-2 = 1022 >= 1000, so host bits = 10, prefix 32-10 = /22. Block size 1024 = four /24s, so it spans 10.20.0.0-10.20.3.255.
- public: 2^7-2 = 126 < 250, 2^8-2 = 254 >= 250, so /24. Starts right after app at 10.20.4.0.
- data: 2^6-2 = 62 < 100, 2^7-2 = 126 >= 100, so /25 (128 addresses). Starts at 10.20.5.0.
- management: 2^4-2 = 14 < 20, 2^5-2 = 30 >= 20, so /27 (32 addresses). Starts at 10.20.5.128 (10.20.5.0 + 128), which is a multiple of 32, so it is aligned.

## NACL for the public subnet (network/nacl.json)
Inbound: 100 deny all from 198.51.100.0/24; 110 allow TCP 80 any; 120 allow TCP 443 any; 130 allow TCP 22 from 10.20.5.128/27;
140 allow TCP 1024-65535 from 10.20.0.0/22 (replies from app).
Outbound: 100 allow TCP 8000 to 10.20.0.0/22; 110 allow TCP 1024-65535 to 0.0.0.0/0 (replies to clients).
Checked with `python tools/nacl_sim.py network/nacl.json network/packets_sample.jsonl --check` -> 6/6.

## Why reply rules, and why order matters
A NACL is stateless: it does not remember that an inbound request opened a connection, so the reply packet is a brand-new packet judged on its own rules. Clients use ephemeral ports 1024-65535, so the reply direction needs an explicit rule for that range (outbound to clients, inbound from the app subnet).
Rules are evaluated from the lowest number upward and the first match wins. The deny for 198.51.100.0/24 is rule 100, below the allows for ports 80/443 (110/120). If it were numbered higher, a packet from that range to port 443 would match the allow first and be let in.
