# uvicorn api.index:app --reload --port 8000
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from abc import ABC, abstractmethod
from typing import List
import io
import struct
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
    """Bộ parse chuyên xử lý định dạng .trc của hãng EXFO"""
    def parse_to_standard_format(self, file_bytes: bytes) -> list:
        raise NotImplementedError("Định dạng .trc hiện tại chưa được nạp lõi thư viện nhị phân.")


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
        ext = filename.split('.')[-1].lower()
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