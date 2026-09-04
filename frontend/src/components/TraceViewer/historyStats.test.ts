import { summarizeExportHistory, type ExportHistoryRecord } from './historyStats';

test('summarizes loaded history using the Vietnam calendar day', () => {
  const history: ExportHistoryRecord[] = [
    {
      id: 1,
      exporter_name: 'A',
      unit: 'QA',
      route_name: 'YBI - TQG',
      export_time: '2026-08-13 01:00:00',
    },
    {
      id: 2,
      exporter_name: 'B',
      unit: 'QA',
      route_name: 'YBI - TQG',
      export_time: '2026-08-13 09:00:00',
    },
    {
      id: 3,
      exporter_name: 'C',
      unit: 'QA',
      route_name: 'HNI - QNH',
      export_time: '2026-08-12 17:30:00',
    },
  ];

  const summary = summarizeExportHistory(
    history,
    new Date('2026-08-12T18:30:00Z'),
  );

  expect(summary.loadedRecords).toBe(3);
  expect(summary.exportsToday).toBe(2);
  expect(summary.uniqueRoutes).toBe(2);
  expect(summary.maximumDailyCount).toBe(2);
  expect(summary.dailyExports).toHaveLength(7);
  expect(summary.dailyExports.at(-1)).toEqual({
    dateKey: '2026-08-13',
    label: '13/08',
    count: 2,
  });
});

test('keeps invalid timestamps out of the daily chart without inventing data', () => {
  const summary = summarizeExportHistory(
    [{
      exporter_name: 'A',
      unit: 'QA',
      route_name: '',
      export_time: 'unknown',
    }],
    new Date('2026-08-13T00:00:00Z'),
  );

  expect(summary.loadedRecords).toBe(1);
  expect(summary.exportsToday).toBe(0);
  expect(summary.uniqueRoutes).toBe(0);
  expect(summary.maximumDailyCount).toBe(0);
});
