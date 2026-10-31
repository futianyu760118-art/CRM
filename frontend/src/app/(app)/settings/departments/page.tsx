'use client';

import { ReloadOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { Button, Space, Table, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';

import { api } from '@/lib/api';
import type { DepartmentItem } from '@/types';

export default function DepartmentsSettingsPage() {
  const { data, isFetching, refetch } = useQuery({
    queryKey: ['settings-departments'],
    queryFn: () => api.get<DepartmentItem[]>('/departments'),
  });

  const columns: ColumnsType<DepartmentItem> = [
    { title: '部门名称', dataIndex: 'name', width: 240 },
    { title: '编码', dataIndex: 'code', width: 140 },
    { title: '排序', dataIndex: 'sort', width: 80 },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (value: string) => (
        <Tag color={value === 'ACTIVE' ? 'green' : 'default'}>{value}</Tag>
      ),
    },
    { title: '备注', dataIndex: 'remark', render: (v: string | null) => v ?? '-' },
  ];

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Space style={{ justifyContent: 'space-between', width: '100%' }}>
        <Typography.Title level={4} style={{ margin: 0 }}>
          组织架构
        </Typography.Title>
        <Button icon={<ReloadOutlined />} onClick={() => refetch()} />
      </Space>
      <Table<DepartmentItem>
        rowKey="id"
        size="small"
        loading={isFetching}
        columns={columns}
        dataSource={data ?? []}
        pagination={false}
        expandable={{ defaultExpandAllRows: true }}
      />
    </Space>
  );
}
