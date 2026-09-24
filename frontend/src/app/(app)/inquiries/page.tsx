'use client';

import { FileExcelOutlined, PlusOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Input, Select, Space, Table, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import Link from 'next/link';
import { useState } from 'react';

import HasPermission from '@/components/HasPermission';
import PageHeader from '@/components/common/PageHeader';
import StatusTag from '@/components/common/StatusTag';
import { API_BASE_URL, api, buildQuery } from '@/lib/api';
import { useAuthStore } from '@/lib/auth-store';
import { formatDate } from '@/lib/format';
import type { PageResult } from '@/types';
import type { Inquiry } from '@/types/business';

function download(url: string, filename: string, token: string | null) {
  fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
    .then((res) => {
      if (!res.ok) throw new Error(`导出失败 (${res.status})`);
      return res.blob();
    })
    .then((blob) => {
      const href = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = href;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(href);
    })
    .catch((e: Error) => window.alert(e.message));
}

export default function InquiriesPage() {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const accessToken = useAuthStore((s) => s.accessToken);
  const [page, setPage] = useState(1);
  const [keyword, setKeyword] = useState('');
  const [status, setStatus] = useState<string | undefined>();

  const query = useQuery({
    queryKey: ['inquiries', page, keyword, status],
    queryFn: () =>
      api.get<PageResult<Inquiry>>(`/inquiries${buildQuery({ page, page_size: 15, keyword, status })}`),
  });

  const submitMutation = useMutation({
    mutationFn: (id: string) => api.post(`/inquiries/${id}/submit`),
    onSuccess: () => {
      message.success('询价已提交');
      queryClient.invalidateQueries({ queryKey: ['inquiries'] });
    },
    onError: (e: Error) => message.error(e.message),
  });

  const columns: ColumnsType<Inquiry> = [
    {
      title: '询价单号',
      dataIndex: 'inquiry_no',
      width: 170,
      fixed: 'left',
      render: (v: string, row) => <Link href={`/inquiries/${row.id}`}>{v}</Link>,
    },
    {
      title: '客户名',
      dataIndex: 'customer_name',
      width: 160,
      ellipsis: true,
      render: (v: string | null, row) => v ?? row.company_name ?? '-',
    },
    { title: '客户编号', dataIndex: 'customer_code', width: 100, render: (v) => v ?? '-' },
    {
      title: '业务员',
      dataIndex: 'owner_name_text',
      width: 100,
      render: (v: string | null, row) => v ?? row.owner_name ?? '-',
    },
    {
      title: '部门',
      dataIndex: 'department_name_text',
      width: 100,
      render: (v: string | null, row) => v ?? row.department_name ?? '-',
    },
    { title: '市场', dataIndex: 'market', width: 100, render: (v) => v ?? '-' },
    {
      title: '新/老',
      dataIndex: 'customer_type',
      width: 80,
      render: (v: string | null) =>
        v ? <Tag color={v === 'NEW' ? 'blue' : 'default'}>{v === 'NEW' ? '新' : '老'}</Tag> : '-',
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 110,
      render: (v: string) => <StatusTag value={v} />,
    },
    {
      title: '明细',
      dataIndex: 'items',
      width: 70,
      render: (_v, row) => row.items?.length ?? '-',
    },
    {
      title: '发起时间',
      dataIndex: 'start_date',
      width: 110,
      render: (v: string | null, row) => formatDate(v ?? row.created_at),
    },
    {
      title: '操作',
      width: 200,
      fixed: 'right',
      render: (_, row) => (
        <Space size={4}>
          <Link href={`/inquiries/${row.id}`}>
            <Button size="small">详情</Button>
          </Link>
          <Button
            size="small"
            icon={<FileExcelOutlined />}
            onClick={() =>
              download(
                `${API_BASE_URL}/inquiries/${row.id}/export-excel`,
                `${row.inquiry_no}.xlsx`,
                accessToken,
              )
            }
          >
            导出
          </Button>
          <HasPermission permission="inquiry:submit">
            <Button
              size="small"
              type="primary"
              ghost
              disabled={row.status !== 'DRAFT'}
              onClick={() => submitMutation.mutate(row.id)}
            >
              提交
            </Button>
          </HasPermission>
        </Space>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        title="询价管理"
        description="按《客户询价单》模板：单据头 16 列 + 明细 22 列，支持导出 Excel 与历史数据"
        extra={
          <Space>
            <Input.Search
              allowClear
              prefix={<SearchOutlined />}
              placeholder="单号 / 需求描述"
              style={{ width: 220 }}
              onSearch={(v) => {
                setPage(1);
                setKeyword(v);
              }}
            />
            <Select
              allowClear
              placeholder="状态"
              style={{ width: 140 }}
              value={status}
              onChange={(v) => {
                setPage(1);
                setStatus(v);
              }}
              options={['DRAFT', 'SUBMITTED', 'PRICING', 'PRICED', 'QUOTED', 'CLOSED'].map((v) => ({
                value: v,
                label: v,
              }))}
            />
            <Button icon={<ReloadOutlined />} onClick={() => query.refetch()} />
            <HasPermission permission="inquiry:create">
              <Link href="/inquiries/new">
                <Button type="primary" icon={<PlusOutlined />}>
                  新建询价
                </Button>
              </Link>
            </HasPermission>
          </Space>
        }
      />

      <Table<Inquiry>
        rowKey="id"
        size="small"
        loading={query.isFetching}
        columns={columns}
        dataSource={query.data?.items ?? []}
        scroll={{ x: 1500 }}
        pagination={{
          current: query.data?.page ?? 1,
          pageSize: query.data?.page_size ?? 15,
          total: query.data?.total ?? 0,
          showSizeChanger: false,
          onChange: setPage,
        }}
      />
    </>
  );
}
