import jsPDF from 'jspdf';
import autoTable from 'jspdf-autotable';
import * as echarts from 'echarts';

export const exportToPdf = async (apiData: any, chartOptions: any, filename: string) => {
  if (!apiData || !apiData.traces || apiData.traces.length === 0) {
    alert("Không có dữ liệu để xuất PDF.");
    return;
  }

  // 1. Create a hidden div to render the wide chart
  const div = document.createElement('div');
  // We use a very wide aspect ratio to stretch the chart horizontally
  div.style.width = '1500px';
  div.style.height = '400px';
  div.style.position = 'absolute';
  div.style.top = '-9999px';
  document.body.appendChild(div);

  // 2. Initialize ECharts and render
  const chart = echarts.init(div, null, { renderer: 'canvas' });
  
  // Clone the options and remove interactive parts
  const exportOptions = JSON.parse(JSON.stringify(chartOptions));
  exportOptions.animation = false;
  exportOptions.dataZoom = []; // Remove zoom controls
  exportOptions.tooltip = { show: false };
  exportOptions.axisPointer = { show: false };
  if (exportOptions.toolbox) {
    exportOptions.toolbox.show = false;
  }
  
  // Also, make sure all markpoints are rendered clearly, without emphasis
  if (exportOptions.series && exportOptions.series.length > 0) {
     exportOptions.series.forEach((seriesItem: any) => {
        if (seriesItem.markPoint) {
           if (seriesItem.markPoint.tooltip) {
               seriesItem.markPoint.tooltip.show = false;
           }
        }
     });
  }

  chart.setOption(exportOptions);

  // Wait a bit for ECharts to fully render the canvas
  await new Promise(resolve => setTimeout(resolve, 200));

  // Get Base64 image
  const imgData = chart.getDataURL({
    type: 'png',
    pixelRatio: 2,
    backgroundColor: '#fff'
  });

  // Cleanup ECharts
  chart.dispose();
  document.body.removeChild(div);

  // 3. Generate PDF
  const pdf = new jsPDF('p', 'mm', 'a4'); // Portrait A4
  const pageWidth = pdf.internal.pageSize.getWidth();
  let cursorY = 15;

  // Title
  pdf.setFontSize(16);
  // Using unaccented Vietnamese to avoid font encoding issues in default jsPDF
  pdf.text("BAO CAO DO KIEM OTDR", pageWidth / 2, cursorY, { align: 'center' });
  cursorY += 10;

  // File name
  pdf.setFontSize(12);
  pdf.text(`File Name: ${filename}`, 15, cursorY);
  cursorY += 8;

  // Details
  const trace = apiData.traces[0];
  const meta = trace.metadata;
  pdf.setFontSize(10);
  pdf.text(`Length: ${meta.fiber_length === 0 ? '' : (meta.fiber_length / 1000).toFixed(3) + ' km'}`, 15, cursorY);
  pdf.text(`Date: ${meta.measurement_date}`, 105, cursorY);
  cursorY += 6;
  pdf.text(`Total Loss: ${meta.total_loss === 0 ? '' : meta.total_loss.toFixed(3) + ' dB'}`, 15, cursorY);
  pdf.text(`Machine: ${meta.machine_type}`, 105, cursorY);
  cursorY += 6;
  pdf.text(`Wavelength: ${meta.wavelength}`, 15, cursorY);
  pdf.text(`Pulse Width: ${meta.pulse_width}`, 105, cursorY);
  cursorY += 6;
  pdf.text(`IOR: ${meta.index_of_refraction}`, 15, cursorY);
  cursorY += 10;

  // Chart image
  // Aspect ratio: 1500 / 400 = 3.75
  // PDF available width = pageWidth - 30 (15mm margin on each side)
  const imgWidth = pageWidth - 30;
  const imgHeight = imgWidth / 3.75; 
  pdf.addImage(imgData, 'PNG', 15, cursorY, imgWidth, imgHeight);
  cursorY += imgHeight + 10;

  // Table
  const tableData = trace.events.map((ev: any) => [
    ev.event_number.toString(),
    ev.event_type,
    Number(ev.distance_km) === 0 ? '0' : Number(ev.distance_km).toFixed(3),
    Number(ev.splice_loss_db) === 0 ? '' : Number(ev.splice_loss_db).toFixed(3),
    (ev.reflectance_db == null || Number(ev.reflectance_db) === 0) ? '' : Number(ev.reflectance_db).toFixed(3),
    Number(ev.slope_db_km) === 0 ? '' : Number(ev.slope_db_km).toFixed(3),
    Number(ev.section_loss_db) === 0 ? '' : Number(ev.section_loss_db).toFixed(3),
    Number(ev.cumulative_loss_db) === 0 ? '' : Number(ev.cumulative_loss_db).toFixed(3)
  ]);

  autoTable(pdf, {
    startY: cursorY,
    head: [['Event', 'Type', 'Distance (km)', 'Loss (dB)', 'Reflectance (dB)', 'Slope (dB/km)', 'Section Loss (dB)', 'Total Loss (dB)']],
    body: tableData,
    theme: 'grid',
    headStyles: { fillColor: [31, 119, 180] },
    styles: { fontSize: 8 },
    margin: { top: 15, bottom: 15, left: 15, right: 15 }
  });

  pdf.save(`${filename.replace(/\.[^/.]+$/, "")}_report.pdf`);
};
