import React from 'react';
import { render, screen } from '@testing-library/react';
import App from './App';

jest.mock('@vercel/blob/client', () => ({ upload: jest.fn() }), {
  virtual: true,
});

beforeEach(() => {
  global.fetch = jest.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ status: 'success', data: [] }),
  });
});

test('renders the trace export screen', () => {
  render(<App />);
  expect(
    screen.getByRole('heading', { name: /Cấu hình Xuất Excel Tuyến/i }),
  ).toBeInTheDocument();
});
