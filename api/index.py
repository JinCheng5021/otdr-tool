# from fastapi import FastAPI, UploadFile, File, HTTPException
# from fastapi.middleware.cors import CORSMiddleware
# from fastapi.responses import JSONResponse
# from abc import ABC, abstractmethod
# from typing import List
# import io
# import struct
# import otdrparser

# app = FastAPI(title="Factory OTDR Core Parser")

# # Cấu hình CORS kết nối Frontend
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# # ==========================================
# # 1. ABSTRACT BASE CLASS (INTERFACE)
# # ==========================================
# class BaseOTDRParser(ABC):
#     """
#     Lớp trừu tượng bắt buộc mọi bộ Parser sau này (.sor, .msor, .trc, .xml...) 
#     đều phải tuân thủ đúng một chuẩn đầu ra duy nhất.
#     """
#     @abstractmethod
#     def parse_to_standard_format(self, file_bytes: bytes) -> list:
#         """Trả về một mảng chứa một hoặc nhiều trace biểu đồ chuẩn hóa"""
#         pass

#     def _extract_standard_blocks(self, blocks_list: list) -> dict:
#         """
#         Hàm dùng chung để chuyển đổi cấu trúc danh sách block của otdrparser 
#         thành cấu trúc dữ liệu chuẩn gọn gàng phục vụ cho Frontend.
#         """
#         import datetime
#         # Chuyển đổi list thành dict dựa trên key 'name' đã thu thập từ Terminal thực tế
#         block_dict = {b.get('name', 'Unknown'): b for b in blocks_list if isinstance(b, dict)}
        
#         # Đọc FxdParams (Dựa chính xác vào cấu trúc key snake_case từ kết quả test)
#         fxd_params = block_dict.get('FxdParams', {})
#         sup_params = block_dict.get('SupParams', {})

#         # Xử lý Ngày đo
#         timestamp = fxd_params.get('date_time')
#         measurement_date = ""
#         if timestamp:
#             measurement_date = datetime.datetime.fromtimestamp(timestamp).strftime('%d/%m/%Y %H:%M:%S')

#         # Xử lý Loại máy
#         vendor = sup_params.get('supplier_name', '')
#         otdr = sup_params.get('otdr_name', '')
#         module = sup_params.get('module_name', '')
#         machine_type = f"{vendor} {otdr} {module}".strip()
#         if not machine_type:
#             machine_type = "Unknown"

#         metadata = {
#             "wavelength": f"{fxd_params.get('wavelength', 0)} nm",
#             "pulse_width": f"{fxd_params.get('pulse_width', 0)} ns",
#             "index_of_refraction": fxd_params.get('index_of_refraction', 1.468),
#             "number_of_data_points": fxd_params.get('number_of_data_points', 0),
#             "measurement_date": measurement_date,
#             "machine_type": machine_type
#         }

#         # Đọc DataPts
#         data_pts_block = block_dict.get('DataPts', {})
#         # Kết quả nội soi xác nhận data_points là list chứa các tuple (distance, loss)
#         raw_points = data_pts_block.get('data_points', [])
#         chart_data = [[float(pt[0]) / 1000.0, float(pt[1])] for pt in raw_points]

#         # Xử lý JDSUEvenementsMTS (nếu có) để lấy section loss chính xác theo thuật toán universal_viavi_parser
#         has_jdsu = 'JDSUEvenementsMTS' in block_dict
#         memory_records = []
#         if has_jdsu:
#             jdsu_content = block_dict['JDSUEvenementsMTS'].get('content', b'')
#             base_offset = 6
#             stride = 140
#             total_bytes = len(jdsu_content)
            
#             offset = base_offset
#             # GIẢI PHÁP SỬA LỖI BIÊN: Chỉ cần đủ 48 bytes để hốt trọn trường Loss và Distance
#             while offset + 48 <= total_bytes:
#                 try:
#                     s_loss = struct.unpack('>d', jdsu_content[offset : offset + 8])[0]
#                     dist_km = struct.unpack('>d', jdsu_content[offset + 40 : offset + 48])[0]
                    
#                     # Loại bỏ các giá trị lỗi Sentinel hoặc giá trị âm rác
#                     if s_loss > -99000.0 and dist_km >= 0:
#                         memory_records.append({
#                             "section_loss": s_loss,
#                             "distance_m": dist_km * 1000.0  # Đồng bộ đơn vị mét
#                         })
#                 except struct.error:
#                     pass
#                 offset += stride

#         # Đọc KeyEvents
#         key_events_block = block_dict.get('KeyEvents', {})
#         raw_events = key_events_block.get('events', [])
#         events = []
#         prev_distance_km = 0.0
#         cumulative_loss_db = 0.0
#         prev_splice_loss = 0.0
        
#         for index, ev in enumerate(raw_events):
#             raw_distance_m = ev.get('distance_of_travel', 0.0)
#             distance_km = float(raw_distance_m) / 1000.0
#             slope = ev.get('slope', 0.0)
            
#             if has_jdsu and memory_records:
#                 matched_loss = 0.000
#                 min_distance_diff = float('inf')
                
#                 # Dò tìm bản ghi nhị phân có khoảng cách tiệm cận nhất với sự kiện chuẩn
#                 for record in memory_records:
#                     diff = abs(record["distance_m"] - raw_distance_m)
#                     if diff < min_distance_diff:
#                         min_distance_diff = diff
#                         matched_loss = record["section_loss"]
                
#                 # Bộ lọc an toàn: Nếu khoảng cách lệch vượt quá 50m, 
#                 # chứng tỏ sự kiện này không có Section Loss thực tế (Vùng mù đầu tuyến hoặc nhiễu)
#                 if min_distance_diff > 50.0:
#                     matched_loss = 0.000
                    
#                 section_loss_db = matched_loss
#             else:
#                 section_loss_db = slope * (distance_km - prev_distance_km)
            
#             if index == 1 and prev_distance_km == 0.0:
#                 # Bỏ qua splice_loss của event đầu tiên nếu khoảng cách = 0
#                 cumulative_loss_db += section_loss_db
#             else:
#                 cumulative_loss_db += section_loss_db + prev_splice_loss
            
#             reflectance = ev.get('reflection_loss', 0.0)
#             if reflectance == 0.0 or reflectance < -10000 or reflectance > 10000:
#                 reflectance = None
            
#             events.append({
#                 "event_number": ev.get('event_number'),
#                 "distance_km": distance_km,
#                 "splice_loss_db": ev.get('splice_loss', 0.0),
#                 "reflectance_db": reflectance,
#                 "slope_db_km": slope,
#                 "section_loss_db": section_loss_db,
#                 "cumulative_loss_db": cumulative_loss_db,
#                 "event_type": ev.get('event_type_details', {}).get('event', 'unknown')
#             })
#             prev_distance_km = distance_km
#             prev_splice_loss = ev.get('splice_loss', 0.0)

#         metadata["total_loss"] = key_events_block.get('total_loss', 0.0)
#         metadata["fiber_length"] = key_events_block.get('fiber_length', 0.0)

#         return {
#             "metadata": metadata,
#             "data": chart_data,
#             "events": events
#         }


# # ==========================================
# # 2. CONCRETE PARSERS (CÁC LỚP XỬ LÝ CỤ THỂ)
# # ==========================================
# class SORParser(BaseOTDRParser):
#     """Bộ parse chuyên xử lý file .sor đơn lẻ"""
#     def parse_to_standard_format(self, file_bytes: bytes) -> list:
#         fp = io.BytesIO(file_bytes)
#         blocks_list = otdrparser.parse(fp)
        
#         # File SOR đơn chỉ chứa duy nhất 1 trace biểu đồ
#         single_trace = self._extract_standard_blocks(blocks_list)
#         single_trace["trace_name"] = "Single Trace"
        
#         return [single_trace]


# class MSORParser(BaseOTDRParser):
#     """Bộ parse chuyên xử lý file phức hợp .msor (Multi-SOR)"""
#     def parse_to_standard_format(self, file_bytes: bytes) -> list:
#         fp = io.BytesIO(file_bytes)
        
#         # Theo thiết kế kiến trúc: bóc toàn bộ các trace trong file đa cấu trúc
#         # Thư viện trả về danh sách các khối liên tục, ta tìm các điểm phân tách
#         all_blocks = otdrparser.parse(fp)
        
#         traces = []
#         current_trace_blocks = []
#         trace_counter = 1
        
#         for block in all_blocks:
#             if not isinstance(block, dict):
#                 continue
            
#             # Mỗi khi gặp block 'Map', tức là một file SOR mới bắt đầu trong file MSOR
#             if block.get('name') == 'Map' and current_trace_blocks:
#                 # Đóng gói cụm block cũ trước khi sang cụm mới
#                 trace_data = self._extract_standard_blocks(current_trace_blocks)
#                 trace_data["trace_name"] = f"Tuyến đo {trace_counter}"
#                 traces.append(trace_data)
#                 trace_counter += 1
#                 current_trace_blocks = []
                
#             current_trace_blocks.append(block)
            
#         # Đóng gói cụm block cuối cùng sót lại trong vòng lặp
#         if current_trace_blocks:
#             trace_data = self._extract_standard_blocks(current_trace_blocks)
#             trace_data["trace_name"] = f"Tuyến đo {trace_counter}"
#             traces.append(trace_data)
            
#         return traces


# class TRCParser(BaseOTDRParser):
#     """Bộ parse chuyên xử lý định dạng .trc của hãng EXFO (Sẵn sàng mở rộng)"""
#     def parse_to_standard_format(self, file_bytes: bytes) -> list:
#         # Định dạng TRC có cấu trúc nhị phân riêng biệt
#         # Khi bạn bổ sung thư viện đọc TRC, chỉ cần viết logic vào đây
#         # Đảm bảo return đúng cấu trúc JSON mảng như SOR và MSOR để Frontend không bị lỗi
#         raise NotImplementedError("Định dạng .trc hiện tại chưa được nạp lõi thư viện nhị phân.")


# # ==========================================
# # 3. PARSER FACTORY (BỘ ĐIỀU HƯỚNG SẢN XUẤT)
# # ==========================================
# class OTDRParserFactory:
#     """Factory Pattern: Tự động nhận diện và trả về đối tượng xử lý phù hợp"""
#     _parsers = {
#         "sor": SORParser,
#         "msor": MSORParser,
#         "trc": TRCParser
#     }

#     @classmethod
#     def get_parser(cls, filename: str) -> BaseOTDRParser:
#         ext = filename.split('.')[-1].lower()
#         parser_class = cls._parsers.get(ext)
        
#         if not parser_class:
#             raise HTTPException(
#                 status_code=400, 
#                 detail=f"Hệ thống chưa hỗ trợ định dạng file '.{ext}'"
#             )
#         return parser_class()


# # ==========================================
# # 4. API ENDPOINT (ỨNG DỤNG CHÍNH)
# # ==========================================
# @app.post("/api/upload-otdr")
# @app.post("/upload-otdr")
# async def upload_otdr(files: List[UploadFile] = File(...)):
#     results = []
    
#     for file in files:
#         file_bytes = await file.read()
        
#         # Sử dụng Factory để lấy đối tượng xử lý mà không cần biết cụ thể nó là class nào
#         parser = OTDRParserFactory.get_parser(file.filename)
        
#         # Thực hiện parse ra cấu trúc chuẩn hóa
#         parsed_traces = parser.parse_to_standard_format(file_bytes)
        
#         results.append({
#             "status": "success",
#             "filename": file.filename,
#             "total_traces": len(parsed_traces),
#             "traces": parsed_traces
#         })
    
#     return JSONResponse(content={
#         "results": results
#     })

# Khởi chạy server local:
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
            "wavelength": f"{fxd_params.get('wavelength', 0)} nm",
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

        # Nhận diện đặc trưng dòng máy Anritsu và Viavi
        is_anritsu = "anritsu" in vendor.lower() or 'ARSpecial' in block_dict
        has_jdsu = 'JDSUEvenementsMTS' in block_dict

        # Thuật toán trích xuất hệ số suy hao định danh (Nominal Slope) ẩn trong ARSpecial
        anritsu_nominal_slope = 0.200  # Fallback tiêu chuẩn cho bước sóng 1550nm
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
        events = []

        # Khởi tạo ma trận tích lũy năng lượng tuyến tính
        prev_distance_km = 0.0
        cumulative_loss_db = 0.0
        prev_splice_loss = 0.0

        # =====================================================================
        # BỘ ĐIỀU HƯỚNG LINH HOẠT CHỐNG BẪY SỰ KIỆN ĐẦU TUYẾN (LAUNCH CABLE ADAPTER)
        # =====================================================================
        fiber_length_field = key_events_block.get('fiber_length', 0.0)
        
        # Chỉ inject Event 1 mốc 0m nếu tổng chiều dài file thô bằng 0 (Đặc trưng file Anritsu gốc như 13.SOR)
        inject_event_1 = is_anritsu and (fiber_length_field == 0.0)
        
        if inject_event_1:
            events.append({
                "event_number": 1,
                "distance_km": 0.0,
                "splice_loss_db": None,
                "reflectance_db": None,
                "slope_db_km": 32.767,  # Giữ nguyên cờ hiệu hiển thị của hãng
                "section_loss_db": None,
                "cumulative_loss_db": 0.0,
                "event_type": "start"
            })
            start_idx = 2
        else:
            start_idx = 1
        
        for index, ev in enumerate(raw_events):
            raw_distance_m = ev.get('distance_of_travel', 0.0)
            distance_km = float(raw_distance_m) / 1000.0
            raw_slope = ev.get('slope', 0.0)
            raw_loss = ev.get('splice_loss', 0.0)
            
            # 1. TÍNH TOÁN SUY HAO ĐOẠN (SECTION LOSS) THEO TỪNG PHÂN LUỒNG HÃNG
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
                # Logic đồng nhất cho Anritsu: Section Loss = Chiều dài chặng trước x Slope hiện tại
                if is_anritsu and raw_slope >= 30.0:
                    # Nếu là sự kiện cuối cùng (EOF), triệt tiêu dốc lỗi bằng hằng số hệ thống ẩn
                    if index == len(raw_events) - 1:
                        display_slope = None
                        calc_slope = anritsu_nominal_slope
                    else:
                        # Nếu là sự kiện uốn cong trung gian, giữ nguyên slope lỗi để nhân trực tiếp
                        display_slope = round(raw_slope, 3)
                        calc_slope = raw_slope
                else:
                    display_slope = round(raw_slope, 3) if raw_slope != 0.0 else 0.0
                    calc_slope = raw_slope
                
                section_loss_db = (distance_km - prev_distance_km) * calc_slope

            # 2. ĐỒNG BỘ HÓA LOGIC HIỂN THỊ THEO THIẾT KẾ GRID UI CỦA FIBERCABLE
            if inject_event_1 and index == 0:
                # Với 13.SOR: Đoạn dây nhảy đầu tiên ép Trống Section Loss hoàn toàn
                section_loss_display = None
                cumulative_loss_db = section_loss_db
            else:
                section_loss_display = round(section_loss_db, 3)
                if index == 0:
                    cumulative_loss_db = section_loss_db
                else:
                    cumulative_loss_db += section_loss_db + prev_splice_loss

            # Làm sạch dữ liệu phản xạ Reflectance chống tràn số âm phản hồi của diode
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
            prev_splice_loss = raw_loss

        # =====================================================================
        # THUẬT TOÁN FALLBACK: TỰ ĐỘNG VÁ KHỐI TÓM TẮT SUMMARY BỊ XOÁ BẰNG 0
        # =====================================================================
        metadata["total_loss"] = key_events_block.get('total_loss', 0.0)
        raw_fiber_length = key_events_block.get('fiber_length', 0.0)

        # 1. Vá lỗi Chiều dài tuyến (fiber_length)
        if is_anritsu and raw_fiber_length == 0.0 and events:
            # Lấy khoảng cách tuyệt đối của sự kiện cuối cùng trong danh sách (m)
            metadata["fiber_length"] = events[-1]["distance_km"] * 1000.0
        else:
            metadata["fiber_length"] = raw_fiber_length

        return {
            "metadata": metadata,
            "data": chart_data,
            "events": events
        }

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
        parser = OTDRParserFactory.get_parser(file.filename)
        parsed_traces = parser.parse_to_standard_format(file_bytes)
        
        results.append({
            "status": "success",
            "filename": file.filename,
            "total_traces": len(parsed_traces),
            "traces": parsed_traces
        })
    
    return JSONResponse(content={"results": results})