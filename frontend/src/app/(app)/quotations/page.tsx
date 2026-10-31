'use client';

import { FileExcelOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { Button, Input, Select, Space, Table } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import Link from 'next/link';
import { useState } from 'react';

import HasPermission from '@/components/HasPermission';
import PageHeader from '@/components/common/PageHeader';
import StatusTag from '@/components/common/StatusTag';
import { API_BASE_URL, api, buildQuery } from '@/lib/api';
import { useAuthStore } from '@/lib/auth-store';
import { formatDate, formatMoney } from '@/lib/format';
import type { PageResult } from '@/types';
import type { Quotation } from '@/types/business';

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

export default function QuotationsPage() {
  const accessToken = useAuthStore((s) => s.accessToken);
  const [page, setPage] = useState(1);
  const [keyword, setKeyword] = useState('');
  const [status, setStatus] = useState<string | undefined>();

  const query = useQuery({
    queryKey: ['quotations', page, keyword, status],
    queryFn: () =>
      api.get<PageResult<Quotation>>(
        `/quotations${buildQuery({ page, page_size: 15, keyword, status })}`,
      ),
  });

  const columns: ColumnsType<Quotation> = [
    {
      title: '报价单号',
      dataIndex: 'quotation_no',
      width: 170,
      fixed: 'left',
      render: (v: string, row) => <Link href={`/quotations/${row.id}`}>{v}</Link>,
    },
    {
      title: '标题',
      dataIndex: 'title',
      width: 170,
      ellipsis: true,
      render: (v: string | null, row) => v ?? <span style={{ color: '#999' }}>Offer</span>,
    },
    { title: '客户', dataIndex: 'company_name', ellipsis: true, render: (v) => v ?? '-' },
    { title: '币种', dataIndex: 'currency', width: 80 },
    {
      title: '合计',
      dataIndex: 'total_amount',
      width: 150,
      render: (v: number | null, row) => formatMoney(v, row.currency),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 130,
      render: (v: string) => <StatusTag value={v} />,
    },
    {
      title: '有效期至',
      dataIndex: 'valid_until',
      width: 120,
      render: (v: string | null) => formatDate(v),
    },
    {
      title: '操作',
      width: 150,
      fixed: 'right',
      render: (_, row) => (
        <Space size={4}>
          <Link href={`/quotations/${row.id}`}>
            <Button size="small">详情</Button>
          </Link>
          <Button
            size="small"
            icon={<FileExcelOutlined />}
            onClick={() =>
              download(
                `${API_BASE_URL}/quotations/${row.id}/export-excel`,
                `${row.quotation_no}.xlsx`,
                accessToken,
              )
            }
          >
            导出
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        title="报价管理"
        description="对外英文价格表：抬头 + Item No./Picture/Description/Price/MOQ/规格列 + ▲条款 + 中英说明"
        extra={
          <Space>
            <Input.Search
              allowClear
              placeholder="单号 / 备注"
              style={{ width: 200 }}
              onSearch={(v) => {
                setPage(1);
                setKeyword(v);
              }}
            />
            <Select
              allowClear
              placeholder="状态"
              style={{ width: 150 }}
              value={status}
              onChange={(v) => {
                setPage(1);
                setStatus(v);
              }}
              options={[
                'DRAFT',
                'PENDING_APPROVAL',
                'APPROVED',
                'SENT',
                'ACCEPTED',
                'REJECTED',
                'EXPIRED',
              ].map((v) => ({ value: v, label: v }))}
            />
            <Button icon={<ReloadOutlined />} onClick={() => query.refetch()} />
            <HasPermission permission="quotation:create">
              <Link href="/quotations/new">
                <Button type="primary" icon={<PlusOutlined />}>
                  新建报价
                </Button>
              </Link>
            </HasPermission>
          </Space>
        }
      />

      <Table<Quotation>
        rowKey="id"
        size="small"
        loading={query.isFetching}
        columns={columns}
        dataSource={query.data?.items ?? []}
        scroll={{ x: 1300 }}
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
