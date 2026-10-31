'use client';

import { ReloadOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Space, Switch, Table, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';

import HasPermission from '@/components/HasPermission';
import { api } from '@/lib/api';
import type { FeatureFlagItem } from '@/types';

export default function FeatureFlagsPage() {
  const { message } = App.useApp();
  const queryClient = useQueryClient();

  const { data, isFetching, refetch } = useQuery({
    queryKey: ['settings-feature-flags'],
    queryFn: () => api.get<FeatureFlagItem[]>('/feature-flags'),
  });

  const toggle = useMutation({
    mutationFn: ({ code, enabled }: { code: string; enabled: boolean }) =>
      api.put(`/feature-flags/${code}`, { enabled }),
    onSuccess: () => {
      message.success('已更新');
      queryClient.invalidateQueries({ queryKey: ['settings-feature-flags'] });
    },
    onError: (error: Error) => message.error(error.message),
  });

  const columns: ColumnsType<FeatureFlagItem> = [
    { title: '开关编码', dataIndex: 'code', width: 220 },
    { title: '名称', dataIndex: 'name', width: 180 },
    { title: '说明', dataIndex: 'description', ellipsis: true },
    {
      title: '状态',
      dataIndex: 'enabled',
      width: 140,
      render: (value: boolean, row) => (
        <HasPermission
          permission="feature_flag:update"
          fallback={<Tag color={value ? 'green' : 'default'}>{value ? 'ON' : 'OFF'}</Tag>}
        >
          <Switch
            checked={value}
            loading={toggle.isPending}
            onChange={(checked) => toggle.mutate({ code: row.code, enabled: checked })}
          />
        </HasPermission>
      ),
    },
  ];

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Space style={{ justifyContent: 'space-between', width: '100%' }}>
        <Typography.Title level={4} style={{ margin: 0 }}>
          功能开关（Feature Flag）
        </Typography.Title>
        <Button icon={<ReloadOutlined />} onClick={() => refetch()} />
      </Space>
      <Table<FeatureFlagItem>
        rowKey="id"
        size="small"
        loading={isFetching}
        columns={columns}
        dataSource={data ?? []}
        pagination={false}
      />
    </Space>
  );
}
