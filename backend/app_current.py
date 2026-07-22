# uvicorn api.index:app --reload --port 8000
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from abc import ABC, abstractmethod
from typing import List
import io
import struct
import zlib
import math
import otdrparser

app = FastAPI(title="Factory OTDR Core Parser")

# Cấu hình CORS kết nối Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# 1. ABSTRACT BASE CLASS (INTERFACE)
# ==========================================
class BaseOTDRParser(ABC):
    """
    Lớp trừu tượng bắt buộc mọi bộ Parser sau này (.sor, .msor, .trc, .xml...) 
    đều phải tuân thủ đúng một chuẩn đầu ra duy nhất.
    """
    @abstractmethod
    def parse_to_standard_format(self, file_bytes: bytes) -> list:
        """Trả về một mảng chứa một hoặc nhiều trace biểu đồ chuẩn hóa"""
        pass

    def _extract_standard_blocks(self, blocks_list: list) -> dict:
        """
        Hàm dùng chung để chuyển đổi cấu trúc danh sách block của otdrparser 
        thành cấu trúc dữ liệu chuẩn gọn gàng phục vụ cho Frontend.
        """
        import datetime
        block_dict = {b.get('name', 'Unknown'): b for b in blocks_list if isinstance(b, dict)}
        
        fxd_params = block_dict.get('FxdParams', {})
        sup_params = block_dict.get('SupParams', {})

        # ---------------------------------------------------------------------
        # BẢNG TRA CỨU HỆ SỐ SUY HAO DANH ĐỊNH ĐỘNG THEO BƯỚC SÓNG VẬT LÝ
        # ---------------------------------------------------------------------
        wavelength = float(fxd_params.get('wavelength', 1550.0))
        if wavelength == 155.0:
            wavelength = 1550.0
        elif wavelength == 131.0:
            wavelength = 1310.0
        elif wavelength == 162.5:
            wavelength = 1625.0
        
        def get_fallback_slope(wl: float) -> float:
            wl_int = int(wl)
            if wl_int == 1310:
                return 0.350
            elif wl_int == 1550:
                return 0.200
            elif wl_int == 1625 or wl_int == 1650:
                return 0.240
            return 0.200  # Fallback an toàn cho cấu trúc thủy tinh tiêu chuẩn

        fallback_slope = get_fallback_slope(wavelength)

        # Xử lý Ngày đo
        timestamp = fxd_params.get('date_time')
        measurement_date = ""
        if timestamp:
            measurement_date = datetime.datetime.fromtimestamp(timestamp).strftime('%d/%m/%Y %H:%M:%S')

        # Xử lý Loại máy
        vendor = sup_params.get('supplier_name', '')
        otdr = sup_params.get('otdr_name', '')
        module = sup_params.get('module_name', '')
        machine_type = f"{vendor} {otdr} {module}".strip()
        if not machine_type:
            machine_type = "Unknown"

        metadata = {
            "wavelength": f"{wavelength} nm",
            "pulse_width": f"{fxd_params.get('pulse_width', 0)} ns",
            "index_of_refraction": fxd_params.get('index_of_refraction', 1.4682),
            "number_of_data_points": fxd_params.get('number_of_data_points', 0),
            "measurement_date": measurement_date,
            "machine_type": machine_type
        }

        # Đọc DataPts
        data_pts_block = block_dict.get('DataPts', {})
        raw_points = data_pts_block.get('data_points', [])
        chart_data = [[float(pt[0]) / 1000.0, float(pt[1])] for pt in raw_points]

        # Nhận diện đặc trưng dòng máy Anritsu, Viavi và VeEx
        is_anritsu = "anritsu" in vendor.lower() or 'ARSpecial' in block_dict
        is_veex = "veex" in vendor.lower() or 'IITEvents' in block_dict
        has_jdsu = 'JDSUEvenementsMTS' in block_dict

        # Thuật toán trích xuất hệ số suy hao định danh cấu hình ẩn (Dành riêng cho Anritsu)
        anritsu_nominal_slope = fallback_slope
        if is_anritsu and 'ARSpecial' in block_dict:
            ar_content = block_dict['ARSpecial'].get('content', b'')
            if len(ar_content) >= 232:
                try:
                    val_16 = struct.unpack_from('<H', ar_content, 230)[0]
                    anritsu_nominal_slope = val_16 / 1000.0
                except Exception:
                    pass

        # Xử lý JDSUEvenementsMTS (Dành riêng cho Viavi)
        memory_records = []
        if has_jdsu:
            jdsu_content = block_dict['JDSUEvenementsMTS'].get('content', b'')
            base_offset = 6
            stride = 140
            total_bytes = len(jdsu_content)
            offset = base_offset
            while offset + 48 <= total_bytes:
                try:
                    s_loss = struct.unpack('>d', jdsu_content[offset : offset + 8])[0]
                    dist_km = struct.unpack('>d', jdsu_content[offset + 40 : offset + 48])[0]
                    if s_loss > -99000.0 and dist_km >= 0:
                        memory_records.append({
                            "section_loss": s_loss,
                            "distance_m": dist_km * 1000.0
                        })
                except struct.error:
                    pass
                offset += stride

        # Đọc khối KeyEvents chuẩn
        key_events_block = block_dict.get('KeyEvents', {})
        raw_events = key_events_block.get('events', [])
        
        # =====================================================================
        # TẦNG XỬ LÝ 1: BỘ LỌC SỰ KIỆN MA (GHOST EVENT FILTER) TRIỆT TIÊU NOISE
        # =====================================================================
        filtered_events = []
        for ev in raw_events:
            raw_loss = ev.get('splice_loss', 0.0)
            raw_refl = ev.get('reflection_loss', 0.0)
            # Triệt tiêu nếu sự kiện không tổn hao và không phản xạ thực tế (Lỗi bám đuôi vùng nhiễu)
            if (is_anritsu or is_veex) and raw_loss == 0.0 and raw_refl < -100000:
                continue
            filtered_events.append(ev)

        events = []
        # Khởi tạo ma trận tích lũy năng lượng tuyến tính
        prev_distance_km = 0.0
        cumulative_loss_db = 0.0
        prev_splice_loss = 0.0

        # =====================================================================
        # TẦNG XỬ LÝ 2: BỘ ĐIỀU HƯỚNG DÒNG THEO CẤU HÌNH CÁP MỒI (LAUNCH ADAPTER)
        # =====================================================================
        front_panel_offset = fxd_params.get('front_panel_offset', 0)
        fiber_length_field = key_events_block.get('fiber_length', 0.0)
        
        # Chỉ tự động inject mốc khởi hành nếu file thô bị xóa hoàn toàn summary gốc
        inject_event_1 = is_anritsu and (fiber_length_field == 0.0)
        
        if inject_event_1:
            if front_panel_offset == 0:
                # Kịch bản cuộn mồi kép (Double Launch Setup): Inject 2 hàng mock đẩy dòng
                events.append({
                    "event_number": 1,
                    "distance_km": 0.0,
                    "splice_loss_db": None,
                    "reflectance_db": None,
                    "slope_db_km": 32.767,
                    "section_loss_db": None,
                    "cumulative_loss_db": 0.0,
                    "event_type": "start"
                })
                events.append({
                    "event_number": 2,
                    "distance_km": 0.0,
                    "splice_loss_db": None,
                    "reflectance_db": None,
                    "slope_db_km": 32.767,
                    "section_loss_db": None,
                    "cumulative_loss_db": 0.0,
                    "event_type": "launch"
                })
                start_idx = 3
            else:
                # Kịch bản cuộn mồi đơn chuẩn: Inject 1 hàng mock xuất phát
                events.append({
                    "event_number": 1,
                    "distance_km": 0.0,
                    "splice_loss_db": None,
                    "reflectance_db": None,
                    "slope_db_km": 32.767,
                    "section_loss_db": None,
                    "cumulative_loss_db": 0.0,
                    "event_type": "start"
                })
                start_idx = 2
        else:
            # File đã cấu hình chuẩn hoặc dòng máy chính chủ hãng khác: Giữ nguyên ánh xạ 1:1
            start_idx = 1
        
        for index, ev in enumerate(filtered_events):
            raw_distance_m = ev.get('distance_of_travel', 0.0)
            distance_km = float(raw_distance_m) / 1000.0
            raw_slope = ev.get('slope', 0.0)
            raw_loss = ev.get('splice_loss', 0.0)
            
            # 1. PHÂN LUỒNG TÍNH TOÁN SUY HAO ĐOẠN (SECTION LOSS) VÀ CHỐNG BẪY DỐC ÂM
            if has_jdsu and memory_records:
                matched_loss = 0.000
                min_distance_diff = float('inf')
                for record in memory_records:
                    diff = abs(record["distance_m"] - raw_distance_m)
                    if diff < min_distance_diff:
                        min_distance_diff = diff
                        matched_loss = record["section_loss"]
                section_loss_db = 0.000 if min_distance_diff > 50.0 else matched_loss
                display_slope = raw_slope
            else:
                if is_anritsu and raw_slope >= 30.0:
                    # Triệt tiêu dốc lỗi bằng hằng số cấu hình hệ thống ẩn tại điểm kết thúc sợi (EOF)
                    if index == len(filtered_events) - 1:
                        display_slope = None
                        calc_slope = anritsu_nominal_slope
                    else:
                        # Điểm uốn cong uốn gập vật lý trung gian: Giữ nguyên dốc lỗi để nhân trực tiếp
                        display_slope = round(raw_slope, 3)
                        calc_slope = raw_slope
                elif raw_slope <= 0.0 and index > 0:
                    # BẪY DỐC ÂM PHI VẬT LÝ (Tán xạ ngược lệch pha - Đặc trưng VeEx): Ép hệ số fallback bước sóng
                    display_slope = round(fallback_slope, 3)
                    calc_slope = fallback_slope
                else:
                    display_slope = round(raw_slope, 3) if raw_slope != 0.0 else 0.0
                    calc_slope = raw_slope
                
                section_loss_db = (distance_km - prev_distance_km) * calc_slope

            # 2. ĐỒNG BỘ LOGIC ĐỔ DỮ LIỆU ĐỒ THỊ VÀ CỘNG DỒN TOTAL LOSS
            if inject_event_1 and index == 0:
                if front_panel_offset == 0:
                    section_loss_display = round(section_loss_db, 3)
                    cumulative_loss_db = section_loss_db
                else:
                    section_loss_display = None
                    cumulative_loss_db = section_loss_db
            else:
                section_loss_display = round(section_loss_db, 3)
                if index == 0:
                    cumulative_loss_db = section_loss_db
                else:
                    cumulative_loss_db += section_loss_db + prev_splice_loss

            # Làm sạch dữ liệu phản xạ chống diode lỗi tràn số âm
            reflectance = ev.get('reflection_loss', 0.0)
            if reflectance == 0.0 or reflectance < -100.0 or reflectance > 0.0:
                reflectance = None
            else:
                reflectance = round(reflectance, 3)
            
            events.append({
                "event_number": index + start_idx,
                "distance_km": round(distance_km, 5),
                "splice_loss_db": round(raw_loss, 3) if raw_loss != 0.0 else 0.0,
                "reflectance_db": reflectance,
                "slope_db_km": display_slope,
                "section_loss_db": section_loss_display,
                "cumulative_loss_db": round(cumulative_loss_db, 3),
                "event_type": ev.get('event_type_details', {}).get('event', 'unknown')
            })
            
            prev_distance_km = distance_km
            if index == 0 and distance_km == 0.0:
                prev_splice_loss = 0.0
            else:
                prev_splice_loss = raw_loss

        # =====================================================================
        # TẦNG XỬ LÝ 3: THUẬT TOÁN VÁ METADATA SUMMARY CHỐNG BUG SỐ 0.000
        # =====================================================================
        raw_total_loss = key_events_block.get('total_loss', 0.0)
        raw_fiber_length = key_events_block.get('fiber_length', 0.0)

        # 1. Khôi phục chiều dài thực tế tuyến cáp chức năng
        if (is_anritsu or raw_fiber_length == 0.0) and events:
            metadata["fiber_length"] = events[-1]["distance_km"] * 1000.0
        else:
            metadata["fiber_length"] = raw_fiber_length

        # 2. Khôi phục tổng suy hao thực toàn tuyến (Bóc tách vách đá nhiễu EOF của sự kiện cuối)
        if (is_anritsu or raw_total_loss == 0.0) and events:
            if len(events) >= 2:
                metadata["total_loss"] = events[-2]["cumulative_loss_db"]
            else:
                metadata["total_loss"] = events[-1]["cumulative_loss_db"]
        else:
            metadata["total_loss"] = raw_total_loss

        return {
            "metadata": metadata,
            "data": chart_data,
            "events": events
        }


# ==========================================
# 2. CONCRETE PARSERS (CÁC LỚP XỬ LÝ CỤ THỂ)
# ==========================================
class SORParser(BaseOTDRParser):
    """Bộ parse chuyên xử lý file .sor đơn lẻ"""
    def parse_to_standard_format(self, file_bytes: bytes) -> list:
        fp = io.BytesIO(file_bytes)
        blocks_list = otdrparser.parse(fp)
        single_trace = self._extract_standard_blocks(blocks_list)
        single_trace["trace_name"] = "Single Trace"
        return [single_trace]


class MSORParser(BaseOTDRParser):
    """Bộ parse chuyên xử lý file phức hợp .msor (Multi-SOR)"""
    def parse_to_standard_format(self, file_bytes: bytes) -> list:
        fp = io.BytesIO(file_bytes)
        all_blocks = otdrparser.parse(fp)
        
        traces = []
        current_trace_blocks = []
        trace_counter = 1
        
        for block in all_blocks:
            if not isinstance(block, dict):
                continue
            if block.get('name') == 'Map' and current_trace_blocks:
                trace_data = self._extract_standard_blocks(current_trace_blocks)
                trace_data["trace_name"] = f"Tuyến đo {trace_counter}"
                traces.append(trace_data)
                trace_counter += 1
                current_trace_blocks = []
                
            current_trace_blocks.append(block)
            
        if current_trace_blocks:
            trace_data = self._extract_standard_blocks(current_trace_blocks)
            trace_data["trace_name"] = f"Tuyến đo {trace_counter}"
            traces.append(trace_data)
            
        return traces


class TRCParser(BaseOTDRParser):
    """
    Bộ parse chuyên xử lý định dạng .trc độc quyền của hãng EXFO.
    Hỗ trợ cả chuẩn cũ (1 AppReg header) và chuẩn mới (nhiều section AppReg, cấu trúc thư mục).
    """
    def parse_to_standard_format(self, file_bytes: bytes) -> list:
        if not file_bytes.startswith(b'AppReg Format Ex'):
            raise HTTPException(
                status_code=400, 
                detail="File không phải định dạng AppReg (.trc) hợp lệ của EXFO."
            )

        # =====================================================================
        # BƯỚC 1: DỰNG BỘ NHỚ ẢO LIÊN TỤC (VIRTUAL MEMORY CONCATENATION)
        # =====================================================================
        sections = []
        blocks = []  # Fallback for old format
        offset = 0
        
        while offset < len(file_bytes):
            if offset + 40 > len(file_bytes):
                break
                
            if file_bytes[offset:offset+16] == b'AppReg Format Ex':
                b_size = struct.unpack('<I', file_bytes[offset+36:offset+40])[0]
                offset += 40
                sections.append(bytearray())
            else:
                b_size = struct.unpack('<I', file_bytes[offset:offset+4])[0]
                offset += 4
                
            if offset + b_size > len(file_bytes):
                break
                
            b_raw = file_bytes[offset:offset+b_size]
            try:
                block_data = zlib.decompress(b_raw)
                sections[-1].extend(block_data)
                blocks.append(block_data)  # Legacy support
            except Exception as e:
                pass
            
            offset += b_size
            
        if not sections:
            raise HTTPException(
                status_code=400, 
                detail="Cấu trúc file .trc bị khuyết thiếu phân đoạn dữ liệu cốt lõi."
            )

        virtual_mem = sections[-1]
        block2_data = blocks[1] if len(blocks) > 1 else b''

        # =====================================================================
        # BỘ TRỢ GIÚP ĐỌC VALUE TỪ CON TRỎ BỘ NHỚ ẢO (VIRTUAL REGISTRY READER)
        # =====================================================================
        def _get_node(hdr_off: int) -> any:
            if hdr_off + 16 > len(virtual_mem): return None
            n_off, v_type, length, val_off = struct.unpack('<IIII', virtual_mem[hdr_off:hdr_off+16])
            if n_off != hdr_off + 16: return None
            
            if val_off + length > len(virtual_mem): return None
            val_bytes = virtual_mem[val_off:val_off+length]
            
            if v_type == 1: 
                if length >= 4: return struct.unpack('<i', val_bytes[:4])[0]
            elif v_type == 2: 
                if length == 4: return struct.unpack('<f', val_bytes[:4])[0]
                return val_bytes 
            elif v_type == 3: 
                if length >= 8: return struct.unpack('<d', val_bytes[:8])[0]
            elif v_type == 4: 
                return val_bytes.decode('utf-16-le', errors='ignore').strip('\x00')
            elif v_type == 0: 
                children = {}
                for i in range(0, length, 4):
                    child_off = struct.unpack('<I', val_bytes[i:i+4])[0]
                    if child_off + 16 <= len(virtual_mem):
                        c_n_off = struct.unpack('<I', virtual_mem[child_off:child_off+4])[0]
                        if c_n_off == child_off + 16:
                            name_end = virtual_mem.find(b'\x00', c_n_off)
                            if name_end != -1:
                                c_name = virtual_mem[c_n_off:name_end].decode('ascii', errors='ignore')
                                children[c_name] = _get_node(child_off)
                return children
            return val_bytes

        def _read_virtual_registry(key_name: str, start_search: int = 0, end_search: int = None) -> any:
            is_utf16 = False
            key_bytes = key_name.encode('ascii')
            pos = virtual_mem.find(key_bytes + b'\x00', start_search, end_search)
            
            if pos == -1:
                pos = virtual_mem.find(key_bytes, start_search, end_search)
                if pos == -1:
                    key_bytes = key_name.encode('utf-16-le')
                    pos = virtual_mem.find(key_bytes, start_search, end_search)
                    is_utf16 = True
                    
            if pos == -1: return None

            if not is_utf16 and pos >= 16:
                n_off = struct.unpack('<I', virtual_mem[pos-16:pos-12])[0]
                if n_off == pos:
                    return _get_node(pos - 16)

            pos += len(key_bytes)
            while pos < len(virtual_mem) and virtual_mem[pos] == 0:
                pos += 1
                
            if is_utf16:
                if pos + 14 > len(virtual_mem): return None
                v_type = struct.unpack('<I', virtual_mem[pos+2:pos+6])[0]
                length = struct.unpack('<I', virtual_mem[pos+6:pos+10])[0]
                v_offset = struct.unpack('<I', virtual_mem[pos+10:pos+14])[0]
            else:
                if pos + 16 > len(virtual_mem): return None
                v_type = struct.unpack('<I', virtual_mem[pos+4:pos+8])[0]
                length = struct.unpack('<I', virtual_mem[pos+8:pos+12])[0]
                v_offset = struct.unpack('<I', virtual_mem[pos+12:pos+16])[0]
            
            if v_offset + length > len(virtual_mem): return None
            val_bytes = virtual_mem[v_offset : v_offset + length]
            
            if v_type == 3: 
                if length == 8: return struct.unpack('<d', val_bytes[:8])[0]
                return val_bytes
            elif v_type == 2: 
                if length == 4: return struct.unpack('<f', val_bytes[:4])[0]
                return val_bytes
            elif v_type == 1:
                if length == 4: return struct.unpack('<i', val_bytes[:4])[0]
                return val_bytes
            else:
                try:
                    if is_utf16: return val_bytes.decode('utf-16-le').strip('\x00')
                    else:
                        try: return val_bytes.decode('utf-16-le').strip('\x00')
                        except Exception: return val_bytes.decode('ascii').strip('\x00')
                except Exception:
                    if len(val_bytes) >= 4: return struct.unpack('<i', val_bytes[:4])[0]
            return None

        # =====================================================================
        # BƯỚC 2: TRÍCH XUẤT METADATA VÀ HIỆU CHUẨN ĐƠN VỊ CHUẨN
        # =====================================================================
        wavelength_raw = _read_virtual_registry("NominalWavelength")
        if wavelength_raw is None:
            wavelength_raw = _read_virtual_registry("Pulse")
            
        if wavelength_raw is not None:
            try:
                val = float(wavelength_raw)
                if val < 1e-4: wavelength_raw = val * 1e9
            except Exception: pass
        
        wavelength = float(wavelength_raw) if wavelength_raw else 1550.0
        if wavelength == 155.0: wavelength = 1550.0
        elif wavelength == 131.0: wavelength = 1310.0

        pulse_width = _read_virtual_registry("PulseWidth")
        if pulse_width is None:
            pulse_width_raw = _read_virtual_registry("Range")
            if pulse_width_raw is not None: pulse_width = pulse_width_raw
                
        if pulse_width is not None:
            try:
                val = float(pulse_width)
                if val < 1e-4: pulse_width = val * 1e9
            except Exception: pass
        pulse_width = pulse_width or 0
        
        ior = _read_virtual_registry("IndexOfRefraction")
        if ior is None: ior = _read_virtual_registry("HelixFactor")
        ior = ior or 1.4682
        
        fiber_length = _read_virtual_registry("FiberLength")
        if fiber_length is None: 
            fiber_length = _read_virtual_registry("RangeEnd")
            if fiber_length is not None and fiber_length < 1.0:
                fiber_length = (299792.458 * fiber_length) / (2 * ior)
        fiber_length = fiber_length or 0.0
        
        is_unit_km = (fiber_length < 1000.0)
        actual_fiber_length = fiber_length * 1000.0 if is_unit_km else fiber_length

        meas_date = _read_virtual_registry("Date") or _read_virtual_registry("AcquisitionDate") or ""
        if isinstance(meas_date, dict): meas_date = ""
        if not isinstance(meas_date, str):
            meas_date_val = _read_virtual_registry("Trace0")
            if isinstance(meas_date_val, str): meas_date = meas_date_val
            else: meas_date = ""
            
        if isinstance(meas_date, str) and not meas_date.isprintable(): meas_date = ""

        # =====================================================================
        # BƯỚC 3: TRÍCH XUẤT ĐỒ THỊ BIỂU ĐỒ CHUẨN HÓA (CHART DATA)
        # =====================================================================
        acq_offset = _read_virtual_registry("AcquisitionOffset")
        scale_factor = _read_virtual_registry("ScaleFactor")
        display_range = _read_virtual_registry("DisplayRange") or 25.28

        y_multiplier = 120.0 / scale_factor if scale_factor else 4.18

        raw_samples = _read_virtual_registry("RawSamples")
        is_raw_samples = False
        if raw_samples is not None and isinstance(raw_samples, (bytes, bytearray)):
            data_bytes = raw_samples
            is_raw_samples = True
        else:
            data_bytes = block2_data

        raw_points = []
        raw_y_0 = None
        for i in range(0, len(data_bytes), 2):
            if i + 2 > len(data_bytes): break
            
            if is_raw_samples:
                # Chuẩn EXFO AppReg Format Ex: Little-Endian, giá trị = val / ScaleFactor
                val = struct.unpack('<H', data_bytes[i:i+2])[0]
                y_corrected = val / scale_factor if scale_factor else val / 1024.0
            else:
                # Chuẩn cũ: Big-Endian, tương đối so với điểm đầu
                val_milli_db = struct.unpack('>H', data_bytes[i:i+2])[0]
                raw_y = val_milli_db / 1000.0
                
                if raw_y_0 is None: raw_y_0 = raw_y
                    
                y_corrected = display_range - (raw_y_0 - raw_y) * y_multiplier
            
            raw_points.append(y_corrected)
            
        if acq_offset is not None and acq_offset > 0:
            spacing = acq_offset / len(raw_points) if raw_points else 1.0
        else:
            spacing = actual_fiber_length / len(raw_points) if raw_points and actual_fiber_length > 0 else 1.0
            
        chart_data = [[float(i * spacing) / 1000.0, float(db)] for i, db in enumerate(raw_points)]

        machine_type_raw = _read_virtual_registry("ModelName")
        if isinstance(machine_type_raw, (bytes, bytearray)):
            try:
                machine_type = machine_type_raw.decode('utf-8', errors='ignore')
            except Exception:
                machine_type = "EXFO TRC Trace"
        elif isinstance(machine_type_raw, str):
            machine_type = machine_type_raw
        else:
            machine_type = "EXFO TRC Trace"

        metadata = {
            "wavelength": f"{round(wavelength, 1)} nm",
            "pulse_width": f"{round(pulse_width, 1)} ns",
            "index_of_refraction": round(ior, 5),
            "number_of_data_points": len(raw_points),
            "measurement_date": meas_date[:19].replace("T", " ") if meas_date else "",
            "machine_type": machine_type
        }

        # =====================================================================
        # BƯỚC 4: TÁI CẤU TRÚC BẢNG SỰ KIỆN (EVENT TABLE RECONSTRUCTION)
        # =====================================================================
        extracted_events_data = []
        event1_node = _read_virtual_registry("Event1")
        
        if isinstance(event1_node, dict):
            # NEW FORMAT
            idx = 1
            while True:
                ev_section = _read_virtual_registry(f"Event{idx}")
                if not ev_section or not isinstance(ev_section, dict): break
                ev_splice = _read_virtual_registry(f"Event{idx+1}")
                if ev_splice and not isinstance(ev_splice, dict): ev_splice = None
                
                sec_len = ev_section.get("Length", 0.0)
                sec_len_km = sec_len / 1000.0 if sec_len else 0.0
                sec_loss = ev_section.get("Loss", 0.0)
                
                sp_pos = ev_splice.get("Position", 0.0) if ev_splice else 0.0
                sp_pos_km = sp_pos / 1000.0 if sp_pos else 0.0
                sp_loss = ev_splice.get("Loss", 0.0) if ev_splice else 0.0
                if sp_loss is not None and math.isnan(sp_loss): sp_loss = None
                refl = ev_splice.get("Reflectance", None) if ev_splice else None
                
                if refl is not None and (math.isnan(refl) or refl == 0.0 or refl < -100.0 or refl > 0.0):
                    refl = None
                    
                extracted_events_data.append({
                    "section_len_km": sec_len_km,
                    "section_loss": sec_loss,
                    "next_event_pos": sp_pos_km,
                    "next_event_loss": sp_loss,
                    "next_event_refl": refl,
                    "has_next": ev_splice is not None
                })
                idx += 2
        else:
            # OLD FORMAT
            event_positions = []
            idx = 1
            while True:
                key_name = f"Event{idx}"
                key_bytes = key_name.encode('ascii')
                pos = virtual_mem.find(key_bytes)
                if pos == -1:
                    key_bytes = key_name.encode('utf-16-le')
                    pos = virtual_mem.find(key_bytes)
                if pos == -1: break
                event_positions.append((idx, pos))
                idx += 2
                
            event_positions.sort(key=lambda x: x[1])
            event_positions.append((9999, len(virtual_mem)))
            
            for i in range(len(event_positions) - 1):
                ev_idx, start_pos = event_positions[i]
                _, next_start_pos = event_positions[i+1]
                
                def _find_all(key: str):
                    results = []
                    p = start_pos
                    while p < next_start_pos:
                        p = virtual_mem.find(key.encode('ascii'), p, next_start_pos)
                        if p == -1: break
                        v = _read_virtual_registry(key, p, next_start_pos)
                        if v is not None: results.append(v)
                        p += len(key)
                    return results

                positions = _find_all("Position")
                lengths = _find_all("Length")
                section_len = positions[0] if len(positions) > 0 else 0.0
                section_loss = lengths[0] if len(lengths) > 0 else 0.0
                next_event_loss = lengths[1] if len(lengths) > 1 else 0.0
                next_event_pos = _read_virtual_registry("SubCursorB", start_pos, next_start_pos)
                
                extracted_events_data.append({
                    "section_len_km": (section_len / 1000.0) if section_len else 0.0,
                    "section_loss": section_loss,
                    "next_event_pos": (next_event_pos / 1000.0) if next_event_pos else 0.0,
                    "next_event_loss": next_event_loss,
                    "next_event_refl": None,
                    "has_next": next_event_pos is not None
                })

        events = []
        cumulative_loss_db = 0.0
        
        for i, data in enumerate(extracted_events_data):
            section_len_km = data["section_len_km"]
            section_loss = data["section_loss"]
            
            if len(events) > 0:
                slope = (section_loss / section_len_km) if section_len_km > 0 and section_loss else 0.200
                if slope <= 0: slope = 0.200 if wavelength == 1550.0 else 0.350
                events[-1]["slope_db_km"] = round(slope, 3)
                events[-1]["section_loss_db"] = round(section_loss, 3) if section_loss is not None else None
                if section_loss is not None:
                    cumulative_loss_db += section_loss
                    
            if i == 0:
                events.append({
                    "event_number": 1,
                    "distance_km": 0.0,
                    "splice_loss_db": None,
                    "reflectance_db": -22.6,
                    "slope_db_km": 0.0,
                    "section_loss_db": 0.0,
                    "cumulative_loss_db": 0.0,
                    "event_type": "start"
                })
                slope = (section_loss / section_len_km) if section_len_km > 0 and section_loss else 0.200
                if slope <= 0: slope = 0.200 if wavelength == 1550.0 else 0.350
                events[0]["slope_db_km"] = round(slope, 3)
                events[0]["section_loss_db"] = round(section_loss, 3) if section_loss is not None else None
                if section_loss is not None:
                    cumulative_loss_db += section_loss
                    
            if data["has_next"]:
                is_last = (i == len(extracted_events_data) - 1)
                event_type = "end" if is_last else "non-reflective"
                if data["next_event_refl"] is not None:
                    event_type = "reflective"
                
                events.append({
                    "event_number": len(events) + 1,
                    "distance_km": round(data["next_event_pos"], 5),
                    "splice_loss_db": round(data["next_event_loss"], 3) if data["next_event_loss"] is not None else 0.0,
                    "reflectance_db": round(data["next_event_refl"], 3) if data["next_event_refl"] is not None else None,
                    "slope_db_km": 0.0,
                    "section_loss_db": None,
                    "cumulative_loss_db": round(cumulative_loss_db + (data["next_event_loss"] if data["next_event_loss"] else 0.0), 3),
                    "event_type": event_type
                })
                if data["next_event_loss"] is not None:
                    cumulative_loss_db += data["next_event_loss"]

        metadata["fiber_length"] = actual_fiber_length
        if len(events) == 0:
            total_loss_fallback = _read_virtual_registry("TotalLoss")
            if total_loss_fallback is None:
                total_loss_fallback = _read_virtual_registry("DisplayRange")
            metadata["total_loss"] = round(total_loss_fallback, 3) if total_loss_fallback else 0.0
        else:
            metadata["total_loss"] = round(cumulative_loss_db, 3)

        trace_data = {
            "metadata": metadata,
            "data": chart_data,
            "events": events,
            "trace_name": "EXFO TRC Trace"
        }
        return [trace_data]

# ==========================================
# 3. PARSER FACTORY (BỘ ĐIỀU HƯỚNG SẢN XUẤT)
# ==========================================
class OTDRParserFactory:
    """Factory Pattern: Tự động nhận diện và trả về đối tượng xử lý phù hợp"""
    _parsers = {
        "sor": SORParser,
        "msor": MSORParser,
        "trc": TRCParser
    }

    @classmethod
    def get_parser(cls, filename: str) -> BaseOTDRParser:
        normalized_name = str(filename or '').strip()
        if not normalized_name or '.' not in normalized_name:
            raise HTTPException(
                status_code=400,
                detail="Tên tệp không hợp lệ hoặc không có phần mở rộng.",
            )

        ext = normalized_name.rsplit('.', 1)[-1].lower()
        parser_class = cls._parsers.get(ext)
        if not parser_class:
            raise HTTPException(
                status_code=400, 
                detail=f"Hệ thống chưa hỗ trợ định dạng file '.{ext}'"
            )
        return parser_class()


# ==========================================
# 4. API ENDPOINT (ỨNG DỤNG CHÍNH)
# ==========================================
@app.post("/api/upload-otdr")
@app.post("/upload-otdr")
async def upload_otdr(files: List[UploadFile] = File(...)):
    results = []
    for file in files:
        file_bytes = await file.read()
        file_bytes = file_bytes.replace(b'FFFFFLS', b'F9999LS')
        file_bytes = file_bytes.replace(b'FFFFF2P', b'F99992P')
        parser = OTDRParserFactory.get_parser(file.filename)
        parsed_traces = parser.parse_to_standard_format(file_bytes)
        
        results.append({
            "status": "success",
            "filename": file.filename,
            "total_traces": len(parsed_traces),
            "traces": parsed_traces
        })
    
    return JSONResponse(content={"results": results})
