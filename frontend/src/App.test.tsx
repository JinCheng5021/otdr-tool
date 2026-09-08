import React from 'react';
import axios from 'axios';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import App from './App';

jest.mock('axios', () => ({
  __esModule: true,
  default: {
    post: jest.fn(),
    isCancel: jest.fn(() => false),
  },
}));
jest.mock('echarts-for-react', () => () => null);

beforeEach(() => {
  window.localStorage.clear();
  window.alert = jest.fn();
  jest.spyOn(console, 'error').mockImplementation(() => undefined);
  (axios.post as jest.Mock).mockReset();
  (axios.post as jest.Mock).mockImplementation(
    async (_url: string, formData: FormData) => {
      const file = formData.get('files') as File;
      return {
        data: {
          results: [{
            status: 'success',
            filename: file.name,
            total_traces: 0,
            traces: [],
          }],
        },
      };
    },
  );
  global.fetch = jest.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ status: 'success', data: [] }),
  });
});

afterEach(() => {
  jest.restoreAllMocks();
});

function exportDropzone(): HTMLElement {
  return screen
    .getByRole('heading', { name: /Kéo thả tệp đo tại đây/i })
    .parentElement as HTMLElement;
}

function openRouteGraph(): void {
  fireEvent.click(
    screen.getAllByRole('button', { name: /Đồ thị tuyến/i })[0],
  );
}

test('renders the trace export screen', () => {
  render(<App />);
  expect(screen.getByRole('img', { name: /^FPT$/i })).toBeInTheDocument();
  expect(screen.getByText(/^PMB - TraceViewer$/i)).toBeInTheDocument();
  expect(screen.queryByText(/^System Ready$/i)).not.toBeInTheDocument();
  expect(
    screen.queryByRole('heading', { name: /Cấu hình Xuất Excel Tuyến/i }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByText(/Chuẩn hóa dữ liệu đo OTDR sang báo cáo kiểm tra tuyến chuyên nghiệp/i),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole('button', { name: /Nạp Trace Mới/i }),
  ).not.toBeInTheDocument();
  expect(screen.queryByText(/^ĐỊNH DẠNG HỖ TRỢ$/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/^THÔNG SỐ XỬ LÝ$/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/^CẤU TRÚC ĐẦU RA$/i)).not.toBeInTheDocument();
});

test('moves parameter modes into system options and keeps basic fields in advanced mode', () => {
  render(<App />);

  expect(screen.queryByText(/Ngưỡng ORL đạt/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/^Nguồn ORL$/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/Khi thiếu ORL đo thật/i)).not.toBeInTheDocument();

  expect(
    screen.queryByRole('button', { name: /^Thông số cơ bản$/i }),
  ).not.toBeInTheDocument();
  fireEvent.click(
    screen.getByRole('button', { name: /^Tùy chọn hệ thống$/i }),
  );

  const basicModeButton = screen.getByRole('button', {
    name: /^Thông số cơ bản$/i,
  });
  const advancedModeButton = screen.getByRole('button', {
    name: /^Thông số nâng cao$/i,
  });

  fireEvent.click(advancedModeButton);
  [
    /^Ngưỡng Event$/i,
    /^Ngưỡng Section Loss$/i,
    /^Thời gian đo \(Duration\)$/i,
    /^Dung sai gom cụm$/i,
    /^Chiều dài tuyến chuẩn$/i,
    /^Sai số đủ tuyến$/i,
    /^Kiểu file đầu ra$/i,
    /^Thông số Core$/i,
  ].forEach((label) => {
    expect(screen.getByText(label)).toBeVisible();
  });
  expect(screen.getByText(/^Xuất section theo$/i)).toBeVisible();

  fireEvent.click(screen.getByRole('button', { name: /Kiểm tra theo đoạn/i }));
  const scopeLabel = screen.getByText(/^Xuất section theo$/i);
  const scopeSelect = scopeLabel.parentElement?.querySelector('select');
  const segmentStart = screen.getByPlaceholderText('Ví dụ: 38.000');
  const segmentEnd = screen.getByPlaceholderText('Ví dụ: 40.000');

  expect(scopeSelect).toHaveValue('selected_range');
  fireEvent.change(segmentStart, { target: { value: '8.5' } });
  fireEvent.change(segmentEnd, { target: { value: '9.5' } });

  fireEvent.click(basicModeButton);
  fireEvent.click(advancedModeButton);

  expect(scopeSelect).toHaveValue('all');
  expect(segmentStart).toHaveValue(null);
  expect(segmentEnd).toHaveValue(null);
});

test('shows route graph navigation in its own header', () => {
  render(<App />);
  openRouteGraph();

  expect(
    screen.getByRole('button', { name: /Trở về Menu/i }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole('heading', { name: /Đồ thị tuyến/i }),
  ).toBeInTheDocument();
});

test('updates session statistics from recognized traces', async () => {
  (axios.post as jest.Mock).mockResolvedValueOnce({
    data: {
      results: [{
        status: 'success',
        filename: 'multi-trace.msor',
        total_traces: 2,
        traces: [],
      }],
    },
  });
  render(<App />);

  fireEvent.drop(exportDropzone(), {
    dataTransfer: { files: [new File(['trace'], 'multi-trace.msor')] },
  });

  await waitFor(() => {
    expect(screen.getByLabelText('Trace nạp')).toHaveTextContent('02');
  });
  expect(screen.getByLabelText('Lỗi nhận diện')).toHaveTextContent('00');
});

test('counts recognition failures and resets them for a replacement batch', async () => {
  (axios.post as jest.Mock)
    .mockRejectedValueOnce(new Error('unrecognized trace'))
    .mockResolvedValueOnce({
      data: {
        results: [{
          status: 'success',
          filename: 'replacement.sor',
          total_traces: 1,
          traces: [],
        }],
      },
    });
  render(<App />);

  fireEvent.drop(exportDropzone(), {
    dataTransfer: { files: [new File(['bad'], 'bad.sor')] },
  });
  await waitFor(() => {
    expect(screen.getByLabelText('Lỗi nhận diện')).toHaveTextContent('01');
  });

  fireEvent.drop(exportDropzone(), {
    dataTransfer: { files: [new File(['good'], 'replacement.sor')] },
  });
  await waitFor(() => {
    expect(screen.getByLabelText('Trace nạp')).toHaveTextContent('01');
    expect(screen.getByLabelText('Lỗi nhận diện')).toHaveTextContent('00');
  });
});

test('automatically analyzes the Excel input batch for the route graph', async () => {
  render(<App />);
  const files = [
    new File(['one'], 'route-a.sor'),
    new File(['two'], 'route-b.sor'),
  ];

  fireEvent.drop(exportDropzone(), {
    dataTransfer: { files },
  });

  await waitFor(() => expect(axios.post).toHaveBeenCalledTimes(2));
  expect(screen.getByText('2 file đã chọn')).toBeInTheDocument();

  openRouteGraph();
  expect(await screen.findByText('route-a.sor')).toBeInTheDocument();
  expect(screen.getByText('route-b.sor')).toBeInTheDocument();
});

test('replaces the complete previous route when a new batch is dropped', async () => {
  render(<App />);
  const firstRoute = [
    new File(['one'], 'wrong-route-1.sor'),
    new File(['two'], 'wrong-route-2.sor'),
  ];
  const secondRoute = [
    new File(['three'], 'correct-route.sor'),
  ];

  fireEvent.drop(exportDropzone(), {
    dataTransfer: { files: firstRoute },
  });
  await waitFor(() => expect(axios.post).toHaveBeenCalledTimes(2));

  fireEvent.drop(exportDropzone(), {
    dataTransfer: { files: secondRoute },
  });
  await waitFor(() => expect(axios.post).toHaveBeenCalledTimes(3));
  expect(screen.getByText('1 file đã chọn')).toBeInTheDocument();

  openRouteGraph();
  expect(await screen.findByText('correct-route.sor')).toBeInTheDocument();
  expect(screen.queryByText('wrong-route-1.sor')).not.toBeInTheDocument();
  expect(screen.queryByText('wrong-route-2.sor')).not.toBeInTheDocument();
});

test('ignores a late response from a route batch that has been replaced', async () => {
  let resolveOldRequest!: (value: unknown) => void;
  (axios.post as jest.Mock)
    .mockReset()
    .mockImplementationOnce(
      () => new Promise((resolve) => {
        resolveOldRequest = resolve;
      }),
    )
    .mockImplementation(async (_url: string, formData: FormData) => {
      const file = formData.get('files') as File;
      return {
        data: {
          results: [{
            status: 'success',
            filename: file.name,
            total_traces: 0,
            traces: [],
          }],
        },
      };
    });

  render(<App />);
  fireEvent.drop(exportDropzone(), {
    dataTransfer: { files: [new File(['old'], 'late-old-route.sor')] },
  });
  await waitFor(() => expect(axios.post).toHaveBeenCalledTimes(1));

  fireEvent.drop(exportDropzone(), {
    dataTransfer: { files: [new File(['new'], 'active-new-route.sor')] },
  });
  await waitFor(() => expect(axios.post).toHaveBeenCalledTimes(2));
  openRouteGraph();
  expect(await screen.findByText('active-new-route.sor')).toBeInTheDocument();

  await act(async () => {
    resolveOldRequest({
      data: {
        results: [{
          status: 'success',
          filename: 'late-old-route.sor',
          total_traces: 0,
          traces: [],
        }],
      },
    });
  });
  expect(screen.queryByText('late-old-route.sor')).not.toBeInTheDocument();
});

test('shares a route-graph input batch back to the Excel export screen', async () => {
  render(<App />);
  openRouteGraph();
  const graphFile = new File(['graph'], 'from-graph.sor');
  const graphInput = document.getElementById('desktop-file-input') as HTMLInputElement;

  fireEvent.change(graphInput, {
    target: { files: [graphFile] },
  });
  await waitFor(() => expect(axios.post).toHaveBeenCalledTimes(1));

  fireEvent.click(screen.getByTitle('Trở về Menu'));
  expect(await screen.findByText('1 file đã chọn')).toBeInTheDocument();
  expect(screen.getByText('from-graph.sor')).toBeInTheDocument();
});

test('loads history and notifications through deploy-safe trace endpoints', async () => {
  render(<App />);

  fireEvent.click(
    screen.getAllByRole('button', { name: /Lịch sử xuất file/i })[0],
  );
  await waitFor(() => {
    expect(global.fetch).toHaveBeenCalledWith('/trace/api/history');
  });

  fireEvent.click(screen.getByRole('button', { name: /^Thông báo$/i }));
  await waitFor(() => {
    expect(global.fetch).toHaveBeenCalledWith('/trace/api/notifications');
  });

  expect(global.fetch).not.toHaveBeenCalledWith(
    expect.stringContaining('localhost:8000'),
  );
});

test('opens the route dashboard and loads the selected region and route', async () => {
  (global.fetch as jest.Mock).mockImplementation(async (url: string) => ({
    ok: true,
    status: 200,
    json: async () => ({
      status: 'success',
      data: url.startsWith('/trace/api/dashboard/routes')
        ? [{ route_key: 'cpa--tyn', route_name: 'TYN - CPA' }]
        : url.startsWith('/trace/api/dashboard/route?')
          ? {
            region: 'B-N',
            route_key: 'cpa--tyn',
            route_name: 'TYN - CPA',
            period_start: '2026-02-01',
            period_end: '2026-07-01',
            months: [
              {
                month: '2026-07', month_label: 'Tháng 7',
                worst_event_loss_db: 4.57, worst_event_position_km: 40.09,
                utilization_percent: 25, dkd_core_percent: 29.17,
                dkd_required_percent: 70, assessment: 'Không đạt',
                loss_source: null, qd_source: null,
              },
            ],
          }
          : [],
    }),
  }));

  render(<App />);
  fireEvent.click(
    screen.getAllByRole('button', { name: /^Biểu đồ$/i })[0],
  );

  expect(
    await screen.findByRole('heading', { name: /^Biểu đồ$/i }),
  ).toBeInTheDocument();
  await waitFor(() => expect(screen.getByLabelText(/Chọn tuyến/i)).toHaveValue('cpa--tyn'));
  expect(global.fetch).toHaveBeenCalledWith(
    '/trace/api/dashboard/routes?region=B-N',
    expect.objectContaining({ signal: expect.anything() }),
  );
  expect(await screen.findByText('Tuyến: TYN - CPA')).toBeInTheDocument();
  expect(
    screen.getByRole('img', { name: /Biểu đồ điểm lỗi nặng theo tháng/i }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole('img', { name: /Biểu đồ đánh giá tuyến theo QĐ 4.8/i }),
  ).toBeInTheDocument();
});

test('does not show estimated route figures when dashboard data cannot be loaded', async () => {
  (global.fetch as jest.Mock).mockResolvedValue({
    ok: false,
    status: 503,
    json: async () => ({ status: 'error' }),
  });

  render(<App />);
  fireEvent.click(
    screen.getAllByRole('button', { name: /^Biểu đồ$/i })[0],
  );

  expect(
    await screen.findByText('Không thể tải danh sách tuyến. Vui lòng thử lại.'),
  ).toBeInTheDocument();
  expect(screen.getByText(/không hiển thị số liệu ước đoán/i)).toBeInTheDocument();
});

test('hides the notification badge when there are no notifications', async () => {
  render(<App />);

  await waitFor(() => {
    expect(global.fetch).toHaveBeenCalledWith('/trace/api/notifications');
  });
  expect(screen.queryByTestId('notification-badge')).not.toBeInTheDocument();
});

test('keeps only unread notifications and removes each one after it is read', async () => {
  (global.fetch as jest.Mock).mockImplementation(async (url: string) => ({
    ok: true,
    json: async () => ({
      status: 'success',
      data: url === '/trace/api/notifications'
        ? [
            { id: 1, message: 'Thông báo 1', export_time: '08:00' },
            { id: 2, message: 'Thông báo 2', export_time: '08:01' },
          ]
        : [],
    }),
  }));

  render(<App />);

  expect(await screen.findByTestId('notification-badge')).toHaveTextContent('2');
  fireEvent.click(screen.getByRole('button', { name: /^Thông báo$/i }));
  expect(screen.getByTestId('notification-badge')).toHaveTextContent('2');
  fireEvent.click(screen.getByRole('button', {
    name: /Đánh dấu đã đọc: Thông báo 1/i,
  }));
  await waitFor(() => {
    expect(screen.getByTestId('notification-badge')).toHaveTextContent('1');
  });
  expect(screen.queryByText('Thông báo 1')).not.toBeInTheDocument();
  expect(screen.getByText('Thông báo 2')).toBeInTheDocument();
  expect(window.localStorage.getItem('otdr_read_notification_ids')).toBe('[1]');

  fireEvent.click(screen.getByRole('button', { name: /^Đọc tất cả$/i }));
  await waitFor(() => {
    expect(screen.queryByTestId('notification-badge')).not.toBeInTheDocument();
  });
  expect(screen.getByText('Không có thông báo chưa đọc.')).toBeInTheDocument();
  expect(window.localStorage.getItem('otdr_last_read_id')).toBe('2');
});

test('restores read state and counts only notifications not previously read', async () => {
  window.localStorage.setItem('otdr_last_read_id', '1');
  window.localStorage.setItem('otdr_read_notification_ids', '[2]');
  (global.fetch as jest.Mock).mockImplementation(async (url: string) => ({
    ok: true,
    json: async () => ({
      status: 'success',
      data: url === '/trace/api/notifications'
        ? [
            { id: 1, message: 'Đã đọc', export_time: '08:00' },
            { id: 2, message: 'Đã đọc riêng', export_time: '08:01' },
            { id: 3, message: 'Chưa đọc', export_time: '08:02' },
          ]
        : [],
    }),
  }));

  render(<App />);

  expect(await screen.findByTestId('notification-badge')).toHaveTextContent('1');
  fireEvent.click(screen.getByRole('button', { name: /^Thông báo$/i }));
  expect(screen.queryByText('Đã đọc')).not.toBeInTheDocument();
  expect(screen.queryByText('Đã đọc riêng')).not.toBeInTheDocument();
  expect(screen.getByText('Chưa đọc')).toBeInTheDocument();
});
