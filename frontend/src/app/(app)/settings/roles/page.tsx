'use client';

import { ReloadOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { Button, Space, Table, Tag, Tooltip, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';

import { api } from '@/lib/api';
import type { PermissionItem, RoleItem } from '@/types';

const SCOPE_LABELS: Record<string, string> = {
  ALL: '全部数据',
  DEPT: '本部门',
  DEPT_AND_CHILD: '本部门及下级',
  SELF: '仅本人',
  CUSTOM: '自定义',
};

export default function RolesSettingsPage() {
  const { data, isFetching, refetch } = useQuery({
    queryKey: ['settings-roles'],
    queryFn: () => api.get<RoleItem[]>('/roles'),
  });

  const { data: permissions } = useQuery({
    queryKey: ['settings-permissions'],
    queryFn: () => api.get<PermissionItem[]>('/permissions'),
  });

  const permissionName = (code: string) =>
    permissions?.find((p) => p.code === code)?.name ?? code;

  const columns: ColumnsType<RoleItem> = [
    { title: '编码', dataIndex: 'code', width: 120 },
    { title: '名称', dataIndex: 'name', width: 140 },
    { title: '说明', dataIndex: 'description', ellipsis: true },
    {
      title: '数据范围',
      dataIndex: 'scope_type',
      width: 140,
      render: (value: string) => <Tag color="purple">{SCOPE_LABELS[value] ?? value}</Tag>,
    },
    {
      title: '权限数',
      dataIndex: 'permission_codes',
      width: 100,
      render: (codes: string[]) =>
        codes.includes('*') ? <Tag color="red">全部</Tag> : <Tag>{codes.length}</Tag>,
    },
    {
      title: '权限明细',
      dataIndex: 'permission_codes',
      render: (codes: string[]) => (
        <Space size={[4, 4]} wrap style={{ maxWidth: 520 }}>
          {codes.slice(0, 8).map((code) => (
            <Tooltip key={code} title={code}>
              <Tag>{permissionName(code)}</Tag>
            </Tooltip>
          ))}
          {codes.length > 8 ? <Tag>+{codes.length - 8}</Tag> : null}
        </Space>
      ),
    },
    {
      title: '内置',
      dataIndex: 'is_system',
      width: 80,
      render: (value: boolean) => (value ? <Tag color="gold">系统</Tag> : '-'),
    },
  ];

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Space style={{ justifyContent: 'space-between', width: '100%' }}>
        <Typography.Title level={4} style={{ margin: 0 }}>
          角色与权限（RBAC + DataScope）
        </Typography.Title>
        <Button icon={<ReloadOutlined />} onClick={() => refetch()} />
      </Space>
      <Table<RoleItem>
        rowKey="id"
        size="small"
        loading={isFetching}
        columns={columns}
        dataSource={data ?? []}
        pagination={false}
      />
      <Typography.Text type="secondary">
        权限点共 {permissions?.length ?? 0} 个；数据范围决定列表接口的可见数据（业务员=仅本人，主管=本部门及下级，其余=全部）。
      </Typography.Text>
    </Space>
  );
}
