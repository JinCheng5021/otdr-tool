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
        # Chuyển đổi list thành dict dựa trên key 'name' đã thu thập từ Terminal thực tế
        block_dict = {b.get('name', 'Unknown'): b for b in blocks_list if isinstance(b, dict)}
        
        # Đọc FxdParams (Dựa chính xác vào cấu trúc key snake_case từ kết quả test)
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
            "index_of_refraction": fxd_params.get('index_of_refraction', 1.468),
            "number_of_data_points": fxd_params.get('number_of_data_points', 0),
            "measurement_date": measurement_date,
            "machine_type": machine_type
        }

        # Đọc DataPts
        data_pts_block = block_dict.get('DataPts', {})
        # Kết quả nội soi xác nhận data_points là list chứa các tuple (distance, loss)
        raw_points = data_pts_block.get('data_points', [])
        chart_data = [[float(pt[0]) / 1000.0, float(pt[1])] for pt in raw_points]

        # Xử lý JDSUEvenementsMTS (nếu có) để lấy section loss chính xác
        has_jdsu = 'JDSUEvenementsMTS' in block_dict
        loss_lookup = {}
        dist_lookup = {}
        if has_jdsu:
            jdsu_content = block_dict['JDSUEvenementsMTS'].get('content', b'')
            base_offset = 6
            stride = 140
            total_bytes = len(jdsu_content)
            for offset in range(base_offset, total_bytes - stride + 1, stride):
                try:
                    s_loss = struct.unpack('>d', jdsu_content[offset : offset + 8])[0]
                    dist_km = struct.unpack('>d', jdsu_content[offset + 40 : offset + 48])[0]
                    evt_idx = struct.unpack('>i', jdsu_content[offset + 68 : offset + 72])[0]
                    
                    if s_loss > -99000.0:
                        loss_lookup[evt_idx] = s_loss
                        dist_lookup[evt_idx] = dist_km * 1000.0
                except struct.error:
                    continue

        # Đọc KeyEvents
        key_events_block = block_dict.get('KeyEvents', {})
        raw_events = key_events_block.get('events', [])
        events = []
        prev_distance_km = 0.0
        cumulative_loss_db = 0.0
        prev_splice_loss = 0.0
        
        for index, ev in enumerate(raw_events):
            raw_distance_m = ev.get('distance_of_travel', 0.0)
            distance_km = float(raw_distance_m) / 1000.0
            slope = ev.get('slope', 0.0)
            
            if has_jdsu:
                section_loss = loss_lookup.get(index, None)
                if section_loss is None:
                    min_diff = float('inf')
                    for idx, d_m in dist_lookup.items():
                        diff = abs(d_m - raw_distance_m)
                        if diff < min_diff and diff < 15.0:
                            min_diff = diff
                            section_loss = loss_lookup[idx]
                
                if section_loss is None or index == 0:
                    section_loss_db = 0.0
                else:
                    section_loss_db = section_loss
            else:
                section_loss_db = slope * (distance_km - prev_distance_km)
            
            if index == 1:
                # Không cộng prev_splice_loss (của event đầu tiên)
                cumulative_loss_db += section_loss_db
            else:
                cumulative_loss_db += section_loss_db + prev_splice_loss
            
            reflectance = ev.get('reflection_loss', 0.0)
            if reflectance == 0.0 or reflectance < -10000 or reflectance > 10000:
                reflectance = None
            
            events.append({
                "event_number": ev.get('event_number'),
                "distance_km": distance_km,
                "splice_loss_db": ev.get('splice_loss', 0.0),
                "reflectance_db": reflectance,
                "slope_db_km": slope,
                "section_loss_db": section_loss_db,
                "cumulative_loss_db": cumulative_loss_db,
                "event_type": ev.get('event_type_details', {}).get('event', 'unknown')
            })
            prev_distance_km = distance_km
            prev_splice_loss = ev.get('splice_loss', 0.0)

        metadata["total_loss"] = key_events_block.get('total_loss', 0.0)
        metadata["fiber_length"] = key_events_block.get('fiber_length', 0.0)

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
        
        # File SOR đơn chỉ chứa duy nhất 1 trace biểu đồ
        single_trace = self._extract_standard_blocks(blocks_list)
        single_trace["trace_name"] = "Single Trace"
        
        return [single_trace]


class MSORParser(BaseOTDRParser):
    """Bộ parse chuyên xử lý file phức hợp .msor (Multi-SOR)"""
    def parse_to_standard_format(self, file_bytes: bytes) -> list:
        fp = io.BytesIO(file_bytes)
        
        # Theo thiết kế kiến trúc: bóc toàn bộ các trace trong file đa cấu trúc
        # Thư viện trả về danh sách các khối liên tục, ta tìm các điểm phân tách
        all_blocks = otdrparser.parse(fp)
        
        traces = []
        current_trace_blocks = []
        trace_counter = 1
        
        for block in all_blocks:
            if not isinstance(block, dict):
                continue
            
            # Mỗi khi gặp block 'Map', tức là một file SOR mới bắt đầu trong file MSOR
            if block.get('name') == 'Map' and current_trace_blocks:
                # Đóng gói cụm block cũ trước khi sang cụm mới
                trace_data = self._extract_standard_blocks(current_trace_blocks)
                trace_data["trace_name"] = f"Tuyến đo {trace_counter}"
                traces.append(trace_data)
                trace_counter += 1
                current_trace_blocks = []
                
            current_trace_blocks.append(block)
            
        # Đóng gói cụm block cuối cùng sót lại trong vòng lặp
        if current_trace_blocks:
            trace_data = self._extract_standard_blocks(current_trace_blocks)
            trace_data["trace_name"] = f"Tuyến đo {trace_counter}"
            traces.append(trace_data)
            
        return traces


class TRCParser(BaseOTDRParser):
    """Bộ parse chuyên xử lý định dạng .trc của hãng EXFO (Sẵn sàng mở rộng)"""
    def parse_to_standard_format(self, file_bytes: bytes) -> list:
        # Định dạng TRC có cấu trúc nhị phân riêng biệt
        # Khi bạn bổ sung thư viện đọc TRC, chỉ cần viết logic vào đây
        # Đảm bảo return đúng cấu trúc JSON mảng như SOR và MSOR để Frontend không bị lỗi
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
        
        # Sử dụng Factory để lấy đối tượng xử lý mà không cần biết cụ thể nó là class nào
        parser = OTDRParserFactory.get_parser(file.filename)
        
        # Thực hiện parse ra cấu trúc chuẩn hóa
        parsed_traces = parser.parse_to_standard_format(file_bytes)
        
        results.append({
            "status": "success",
            "filename": file.filename,
            "total_traces": len(parsed_traces),
            "traces": parsed_traces
        })
    
    return JSONResponse(content={
        "results": results
    })

# Khởi chạy server local:
# uvicorn main:app --reload --port 8000