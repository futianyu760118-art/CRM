'use client';

import { ReloadOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { Button, Space, Table, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';

import { api } from '@/lib/api';
import type { DictionaryItem } from '@/types';

export default function DictionariesPage() {
  const { data, isFetching, refetch } = useQuery({
    queryKey: ['settings-dictionaries'],
    queryFn: () => api.get<DictionaryItem[]>('/dictionaries'),
  });

  const columns: ColumnsType<DictionaryItem> = [
    { title: '字典类型', dataIndex: 'dict_type', width: 200 },
    { title: '标签', dataIndex: 'label', width: 180 },
    { title: '值', dataIndex: 'value', width: 180 },
    { title: '排序', dataIndex: 'sort', width: 80 },
    {
      title: '启用',
      dataIndex: 'enabled',
      width: 100,
      render: (value: boolean) => (
        <Tag color={value ? 'green' : 'default'}>{value ? '启用' : '停用'}</Tag>
      ),
    },
  ];

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Space style={{ justifyContent: 'space-between', width: '100%' }}>
        <Typography.Title level={4} style={{ margin: 0 }}>
          数据字典
        </Typography.Title>
        <Button icon={<ReloadOutlined />} onClick={() => refetch()} />
      </Space>
      <Table<DictionaryItem>
        rowKey="id"
        size="small"
        loading={isFetching}
        columns={columns}
        dataSource={data ?? []}
        pagination={{ pageSize: 15 }}
      />
    </Space>
  );
}
