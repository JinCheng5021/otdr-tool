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

jest.mock('@vercel/blob/client', () => ({ upload: jest.fn() }), {
  virtual: true,
});
jest.mock('axios', () => ({
  __esModule: true,
  default: {
    post: jest.fn(),
    isCancel: jest.fn(() => false),
  },
}));
jest.mock('echarts-for-react', () => () => null);

beforeEach(() => {
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
  expect(
    screen.getByRole('heading', { name: /Cấu hình Xuất Excel Tuyến/i }),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole('button', { name: /Nạp Trace Mới/i }),
  ).not.toBeInTheDocument();
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
