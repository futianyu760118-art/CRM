'use client';

import { PlusOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  App,
  Button,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useState } from 'react';

import HasPermission from '@/components/HasPermission';
import { api, buildQuery } from '@/lib/api';
import type { DepartmentItem, PageResult, RoleItem, SystemUser } from '@/types';

interface CreateUserForm {
  username: string;
  code: string;
  password: string;
  name: string;
  email?: string;
  department_id?: string;
  role_ids?: string[];
}

function flattenDepartments(nodes: DepartmentItem[], depth = 0): { label: string; value: string }[] {
  return nodes.flatMap((node) => [
    { label: `${'　'.repeat(depth)}${node.name}`, value: node.id },
    ...flattenDepartments(node.children ?? [], depth + 1),
  ]);
}

export default function UsersSettingsPage() {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [keyword, setKeyword] = useState('');
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm<CreateUserForm>();

  const { data, isFetching, refetch } = useQuery({
    queryKey: ['settings-users', page, keyword],
    queryFn: () =>
      api.get<PageResult<SystemUser>>(
        `/users${buildQuery({ page, page_size: 10, keyword })}`,
      ),
  });

  const { data: roles } = useQuery({
    queryKey: ['settings-roles'],
    queryFn: () => api.get<RoleItem[]>('/roles'),
  });

  const { data: departments } = useQuery({
    queryKey: ['settings-departments'],
    queryFn: () => api.get<DepartmentItem[]>('/departments'),
  });

  const createMutation = useMutation({
    mutationFn: (values: CreateUserForm) => api.post<SystemUser>('/users', values),
    onSuccess: () => {
      message.success('用户创建成功');
      setOpen(false);
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ['settings-users'] });
    },
    onError: (error: Error) => message.error(error.message),
  });

  const columns: ColumnsType<SystemUser> = [
    {
      title: '业务员编号',
      dataIndex: 'code',
      width: 120,
      render: (value: string | null) =>
        value ? (
          <Tag color="blue">{value}</Tag>
        ) : (
          <Tooltip title="未维护业务员编号时，新建客户将回退为 CUS-xxxx 编码">
            <Tag color="orange">未设置</Tag>
          </Tooltip>
        ),
    },
    { title: '账号', dataIndex: 'username', width: 140 },
    { title: '姓名', dataIndex: 'name', width: 140 },
    {
      title: '部门',
      dataIndex: 'department_name',
      width: 140,
      render: (value: string | null) => value ?? '-',
    },
    {
      title: '角色',
      dataIndex: 'roles',
      render: (values: string[]) =>
        values.length ? values.map((r) => <Tag key={r} color="blue">{r}</Tag>) : '-',
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (value: string) => (
        <Tag color={value === 'ACTIVE' ? 'green' : 'default'}>{value}</Tag>
      ),
    },
    {
      title: '最近登录',
      dataIndex: 'last_login_at',
      width: 190,
      render: (value: string | null) => (value ? new Date(value).toLocaleString() : '-'),
    },
  ];

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Space wrap style={{ justifyContent: 'space-between', width: '100%' }}>
        <Typography.Title level={4} style={{ margin: 0 }}>
          用户管理
        </Typography.Title>
        <Space>
          <Input
            allowClear
            prefix={<SearchOutlined />}
            placeholder="搜索账号/姓名/邮箱"
            style={{ width: 220 }}
            onPressEnter={(e) => {
              setPage(1);
              setKeyword((e.target as HTMLInputElement).value);
            }}
          />
          <Button icon={<ReloadOutlined />} onClick={() => refetch()} />
          <HasPermission permission="user:create">
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>
              新建用户
            </Button>
          </HasPermission>
        </Space>
      </Space>

      <Table<SystemUser>
        rowKey="id"
        size="small"
        loading={isFetching}
        columns={columns}
        dataSource={data?.items ?? []}
        pagination={{
          current: data?.page ?? 1,
          pageSize: data?.page_size ?? 10,
          total: data?.total ?? 0,
          onChange: setPage,
        }}
      />

      <Modal
        title="新建用户"
        open={open}
        onCancel={() => setOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={createMutation.isPending}
        destroyOnClose
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={(values) => createMutation.mutate(values)}
          requiredMark={false}
        >
          <Form.Item name="username" label="账号" rules={[{ required: true }]}>
            <Input placeholder="登录账号" />
          </Form.Item>
          <Form.Item
            name="code"
            label="业务员编号"
            tooltip="K3 职员编号，格式 HJ+3位，例如 HJ003；用于生成客户编码 HJ003-176-576"
          >
            <Input placeholder="如 HJ003（可留空，后续补录）" />
          </Form.Item>
          <Form.Item
            name="password"
            label="初始密码"
            rules={[{ required: true, min: 6, message: '至少 6 位' }]}
          >
            <Input.Password placeholder="至少 6 位" />
          </Form.Item>
          <Form.Item name="name" label="姓名" rules={[{ required: true }]}>
            <Input placeholder="真实姓名" />
          </Form.Item>
          <Form.Item name="email" label="邮箱">
            <Input placeholder="name@example.com" />
          </Form.Item>
          <Form.Item name="department_id" label="部门">
            <Select
              allowClear
              placeholder="选择部门"
              options={flattenDepartments(departments ?? [])}
            />
          </Form.Item>
          <Form.Item name="role_ids" label="角色">
            <Select
              mode="multiple"
              placeholder="选择角色"
              options={(roles ?? []).map((r) => ({ label: r.name, value: r.id }))}
            />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}
