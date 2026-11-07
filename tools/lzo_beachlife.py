import sys
import struct
import os

def decompress_biz_chunk(src, expected_size=65536):
    dst = bytearray()
    esi = 0
    
    if len(src) < 2:
        return dst
        
    cl = src[esi]; esi += 1
    dl = src[esi]; esi += 1
    ecx = (cl << 8) + dl
    if (ecx >> 8) & 1:
        esi += 3
        
    esi += 3 
    
    while esi < len(src):
        cmd = src[esi]
        esi += 1
        
        try:
            if cmd < 0x80:
                lit_len = cmd & 3
                if esi >= len(src): break
                dl = src[esi]; esi += 1
                for _ in range(lit_len):
                    dst.append(src[esi])
                    esi += 1
                
                offset = ((cmd & 0x60) << 3) + dl + 1
                match_len = ((cmd >> 2) & 7) + 3
                
                for _ in range(match_len):
                    dst.append(dst[-offset])
                    
            elif (cmd & 0xC0) == 0x80: 
                if esi + 1 >= len(src): break
                dl = src[esi]; esi += 1
                bl = src[esi]; esi += 1
                
                lit_len = dl >> 6
                for _ in range(lit_len):
                    dst.append(src[esi])
                    esi += 1
                    
                offset = ((dl & 0x3F) << 8) + bl + 1
                match_len = (cmd & 0x3F) + 4
                
                for _ in range(match_len):
                    dst.append(dst[-offset])
                    
            elif (cmd & 0xE0) == 0xC0: 
                if esi + 2 >= len(src): break
                b1 = src[esi]; esi += 1
                b2 = src[esi]; esi += 1
                b3 = src[esi]; esi += 1
                
                lit_len = cmd & 3
                for _ in range(lit_len):
                    dst.append(src[esi])
                    esi += 1
                    
                offset = ((cmd & 0x10) << 12) + (b1 << 8) + b2 + 1
                match_len = ((cmd & 0x0C) << 6) + b3 + 5
                
                for _ in range(match_len):
                    dst.append(dst[-offset])
                    
            else: 
                if cmd < 0xFC:
                    lit_len = ((cmd & 0x1F) + 1) * 4
                    for _ in range(lit_len):
                        dst.append(src[esi])
                        esi += 1
                else:
                    lit_len = cmd & 3
                    for _ in range(lit_len):
                        dst.append(src[esi])
                        esi += 1
                    break 
        except Exception as e:
            print(f"CRASH! cmd={hex(cmd)} len(dst)={len(dst)} esi={esi}")
            break
            
    return dst

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python lzo_beachlife.py <file.biz>")
        sys.exit(1)
        
    biz_path = sys.argv[1]
    with open(biz_path, 'rb') as f:
        d = f.read()
        
    offsets = struct.unpack('<1024I', d[0:4096])
    sizes = struct.unpack('<1024I', d[4096:8192])
    
    out_dir = biz_path + "_unpacked"
    os.makedirs(out_dir, exist_ok=True)
    
    print(f"Extracting chunks to {out_dir} ...")
    count = 0
    
    for idx in range(1024):
        if sizes[idx] == 0:
            continue
            
        chunk_data = d[offsets[idx]:offsets[idx]+sizes[idx]]
        res = decompress_biz_chunk(chunk_data)
        
        out_file = os.path.join(out_dir, f"chunk_{idx:03d}.bin")
        with open(out_file, 'wb') as f:
            f.write(res)
            
        count += 1
        if count % 50 == 0:
            print(f"Extracted {count} chunks...")
            
    print(f"Successfully extracted {count} chunks!")
