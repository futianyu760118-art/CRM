'use client';

import { ReloadOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { Button, Space, Table, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useState } from 'react';

import { api, buildQuery } from '@/lib/api';
import type { AuditLogItem, PageResult } from '@/types';

const ACTION_COLORS: Record<string, string> = {
  CREATE: 'green',
  UPDATE: 'blue',
  DELETE: 'red',
  LOGIN: 'purple',
};

export default function AuditLogsPage() {
  const [page, setPage] = useState(1);
  const { data, isFetching, refetch } = useQuery({
    queryKey: ['settings-audit-logs', page],
    queryFn: () =>
      api.get<PageResult<AuditLogItem>>(`/audit-logs${buildQuery({ page, page_size: 15 })}`),
  });

  const columns: ColumnsType<AuditLogItem> = [
    {
      title: '时间',
      dataIndex: 'created_at',
      width: 180,
      render: (value: string) => new Date(value).toLocaleString(),
    },
    { title: '用户', dataIndex: 'username', width: 120, render: (v: string | null) => v ?? '-' },
    { title: '模块', dataIndex: 'module', width: 120 },
    {
      title: '动作',
      dataIndex: 'action',
      width: 100,
      render: (value: string) => <Tag color={ACTION_COLORS[value] ?? 'default'}>{value}</Tag>,
    },
    { title: '方法', dataIndex: 'method', width: 90 },
    { title: '路径', dataIndex: 'path', ellipsis: true },
    {
      title: '结果',
      dataIndex: 'success',
      width: 90,
      render: (value: boolean, row) => (
        <Tag color={value ? 'green' : 'red'}>{row.status_code}</Tag>
      ),
    },
    { title: '耗时(ms)', dataIndex: 'duration_ms', width: 100 },
    { title: 'IP', dataIndex: 'ip', width: 130, render: (v: string | null) => v ?? '-' },
  ];

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Space style={{ justifyContent: 'space-between', width: '100%' }}>
        <Typography.Title level={4} style={{ margin: 0 }}>
          审计日志
        </Typography.Title>
        <Button icon={<ReloadOutlined />} onClick={() => refetch()} />
      </Space>
      <Table<AuditLogItem>
        rowKey="id"
        size="small"
        loading={isFetching}
        columns={columns}
        dataSource={data?.items ?? []}
        pagination={{
          current: data?.page ?? 1,
          pageSize: data?.page_size ?? 15,
          total: data?.total ?? 0,
          onChange: setPage,
        }}
      />
    </Space>
  );
}
