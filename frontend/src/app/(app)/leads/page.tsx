'use client';

import { PlusOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  App,
  Button,
  Drawer,
  Form,
  Input,
  Modal,
  Radio,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useState } from 'react';

import HasPermission from '@/components/HasPermission';
import PageHeader from '@/components/common/PageHeader';
import StatusTag from '@/components/common/StatusTag';
import { ApiError, api, buildQuery } from '@/lib/api';
import {
  CONTACT_RELATION_OPTIONS,
  LEAD_CHANNELS,
  LEAD_CHANNEL_OPTIONS,
  LEAD_LEVELS,
  LEAD_LEVEL_OPTIONS,
  labelOf,
} from '@/lib/dictionaries';
import { formatDateTime } from '@/lib/format';
import type { PageResult } from '@/types';
import type {
  DuplicateConflictData,
  DuplicateResult,
  Lead,
} from '@/types/business';

interface UserOption {
  id: string;
  name: string;
  username: string;
  department_name: string | null;
}

type LeadFormValues = {
  name: string;
  contact_name?: string;
  email?: string;
  phone?: string;
  country?: string;
  source?: string;
  lead_level?: string;
  channel?: string;
  requirement_text?: string;
  background?: string;
  remark?: string;
};

function conflictData(error: unknown): DuplicateConflictData | null {
  if (!(error instanceof ApiError) || error.status !== 409) return null;
  const data = error.data as Partial<DuplicateConflictData> | undefined;
  if (!data || !Array.isArray(data.candidates)) return null;
  return {
    candidates: data.candidates,
    definite: data.definite ?? [],
    suspected: data.suspected ?? [],
    truncated: data.truncated ?? false,
    total: data.total ?? data.candidates.length,
  };
}

export default function LeadsPage() {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [keyword, setKeyword] = useState('');
  const [status, setStatus] = useState<string | undefined>();
  const [leadLevel, setLeadLevel] = useState<string | undefined>();
  const [channel, setChannel] = useState<string | undefined>();
  const [ownerId, setOwnerId] = useState<string | undefined>();
  const [overdue, setOverdue] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [assignTarget, setAssignTarget] = useState<Lead | null>(null);
  const [dedup, setDedup] = useState<{ values: LeadFormValues; result: DuplicateConflictData } | null>(null);
  const [dedupNote, setDedupNote] = useState('');
  const [convertTarget, setConvertTarget] = useState<Lead | null>(null);
  const [convertCandidates, setConvertCandidates] = useState<DuplicateConflictData | null>(null);
  const [convertForm] = Form.useForm<{
    mode: 'link' | 'create';
    link_company_id?: string;
    non_duplicate_reason?: string;
    relation_type?: string;
  }>();
  const [form] = Form.useForm<LeadFormValues>();
  const [assignForm] = Form.useForm<{ owner_id: string }>();

  const { data, isFetching, refetch } = useQuery({
    queryKey: ['leads', page, keyword, status, leadLevel, channel, ownerId, overdue],
    queryFn: () =>
      api.get<PageResult<Lead>>(
        `/leads${buildQuery({
          page,
          page_size: 10,
          keyword,
          status,
          lead_level: leadLevel,
          channel,
          owner_id: ownerId,
          overdue: overdue ? 1 : undefined,
        })}`,
      ),
  });

  const { data: users } = useQuery({
    queryKey: ['user-options'],
    queryFn: () => api.get<UserOption[]>('/users/options'),
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['leads'] });

  const createMutation = useMutation({
    mutationFn: (values: LeadFormValues & { force?: boolean; dedup_note?: string }) =>
      api.post('/leads', values),
    onSuccess: () => {
      message.success('线索创建成功');
      setCreateOpen(false);
      setDedup(null);
      setDedupNote('');
      form.resetFields();
      invalidate();
    },
    onError: (e: Error) => message.error(e.message),
  });

  const startCreate = async (values: LeadFormValues) => {
    let result: DuplicateResult;
    try {
      result = await api.post<DuplicateResult>('/leads/check-duplicate', {
        name: values.name,
        email: values.email || undefined,
        phone: values.phone || undefined,
      });
    } catch (e) {
      message.error((e as Error).message);
      return;
    }
    if (result.definite.length || result.suspected.length) {
      setDedupNote('');
      setDedup({
        values,
        result: {
          ...result,
          candidates: [...result.definite, ...result.suspected],
        },
      });
      return;
    }
    createMutation.mutate(values);
  };

  const confirmDedupCreate = () => {
    if (!dedup) return;
    const needsNote = dedup.result.definite.length > 0;
    if (needsNote && !dedupNote.trim()) {
      message.warning('请填写查重说明后再确认创建');
      return;
    }
    createMutation.mutate({
      ...dedup.values,
      force: true,
      dedup_note: dedupNote.trim() || '已知悉疑似重复，确认创建',
    });
  };

  const assignMutation = useMutation({
    mutationFn: ({ id, owner }: { id: string; owner: string }) =>
      api.post(`/leads/${id}/assign`, { owner_id: owner }),
    onSuccess: () => {
      message.success('线索已分配');
      setAssignTarget(null);
      assignForm.resetFields();
      invalidate();
    },
    onError: (e: Error) => message.error(e.message),
  });

  const convertMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Record<string, unknown> }) =>
      api.post(`/leads/${id}/convert`, payload),
    onSuccess: (data) => {
      const result = data as { company_code: string; linked_existing: boolean };
      message.success(
        result.linked_existing
          ? `已关联既有客户 ${result.company_code}`
          : `已转为客户 ${result.company_code}`,
      );
      setConvertTarget(null);
      setConvertCandidates(null);
      convertForm.resetFields();
      queryClient.invalidateQueries({ queryKey: ['customers'] });
      invalidate();
    },
    onError: (e: Error) => {
      const conflict = conflictData(e);
      if (conflict && convertTarget) {
        setConvertCandidates(conflict);
        convertForm.setFieldsValue({
          mode: 'link',
          link_company_id: conflict.candidates.find((c) => c.company_id)?.company_id ?? undefined,
          relation_type: 'OTHER',
        });
        return;
      }
      message.error(e.message);
    },
  });

  const openConvert = (row: Lead) => {
    setConvertTarget(row);
    setConvertCandidates(null);
    convertForm.resetFields();
    convertForm.setFieldsValue({ mode: 'create', relation_type: 'OTHER' });
  };

  const submitConvert = (values: {
    mode: 'link' | 'create';
    link_company_id?: string;
    non_duplicate_reason?: string;
    relation_type?: string;
  }) => {
    if (!convertTarget) return;
    const payload: Record<string, unknown> = {
      create_contact: true,
      customer_level: 'B',
      relation_type: values.relation_type ?? 'OTHER',
    };
    if (values.mode === 'link') {
      if (!values.link_company_id) {
        message.warning('请选择要关联的既有客户');
        return;
      }
      payload.link_company_id = values.link_company_id;
    } else if (values.non_duplicate_reason) {
      payload.non_duplicate_reason = values.non_duplicate_reason;
    }
    convertMutation.mutate({ id: convertTarget.id, payload });
  };

  const isOverdue = (value?: string | null) => !!value && new Date(value).getTime() < Date.now();

  const columns: ColumnsType<Lead> = [
    { title: '线索编号', dataIndex: 'lead_no', width: 160 },
    { title: '公司名称', dataIndex: 'name', ellipsis: true },
    { title: '联系人', dataIndex: 'contact_name', width: 110, render: (v) => v ?? '-' },
    {
      title: '等级',
      dataIndex: 'lead_level',
      width: 130,
      render: (v: string | null) =>
        v ? <Tag color={v === 'A' ? 'red' : v === 'B' ? 'blue' : 'default'}>{labelOf(LEAD_LEVELS, v)}</Tag> : '-',
    },
    {
      title: '渠道分类',
      dataIndex: 'channel',
      width: 110,
      render: (v: string | null) => labelOf(LEAD_CHANNELS, v),
    },
    { title: '负责人', dataIndex: 'owner_name', width: 100, render: (v) => v ?? '-' },
    {
      title: '最近跟进',
      dataIndex: 'last_followup_at',
      width: 160,
      render: (v: string | null) => (v ? formatDateTime(v) : '—'),
    },
    {
      title: '下次跟进',
      dataIndex: 'next_due_date',
      width: 160,
      render: (v: string | null) =>
        v ? (
          <Typography.Text type={isOverdue(v) ? 'danger' : undefined}>
            {formatDateTime(v)}
            {isOverdue(v) ? '（逾期）' : ''}
          </Typography.Text>
        ) : (
          '—'
        ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (v: string) => <StatusTag value={v} />,
    },
    {
      title: '操作',
      width: 180,
      fixed: 'right',
      render: (_, row) => (
        <Space size={4}>
          <HasPermission permission="lead:assign">
            <Button
              size="small"
              disabled={row.status === 'CONVERTED'}
              onClick={() => {
                setAssignTarget(row);
                assignForm.setFieldsValue({ owner_id: row.owner_id ?? '' });
              }}
            >
              分配
            </Button>
          </HasPermission>
          <HasPermission permission="lead:convert">
            <Button
              size="small"
              type="primary"
              ghost
              disabled={row.status === 'CONVERTED' || row.status === 'INVALID'}
              onClick={() => openConvert(row)}
            >
              {row.status === 'CONVERTED' ? '已转化' : '转客户'}
            </Button>
          </HasPermission>
        </Space>
      ),
    },
  ];

  const candidateColumns: ColumnsType<DuplicateConflictData['candidates'][number]> = [
    { title: '编号', dataIndex: 'ref', width: 130 },
    { title: '名称', dataIndex: 'name', render: (v) => v ?? '-' },
    { title: '类型', dataIndex: 'kind', width: 90, render: (v) => ({ lead: '线索', customer: '客户', contact: '联系人' }[v as string] ?? v) },
    { title: '命中原因', dataIndex: 'reason', render: (v) => v ?? '-' },
    { title: '负责人', dataIndex: 'owner_name', width: 90, render: (v) => v ?? '-' },
    {
      title: '最近跟进',
      dataIndex: 'last_followup_at',
      width: 150,
      render: (v: string | null) => (v ? formatDateTime(v) : '—'),
    },
  ];

  return (
    <>
      <PageHeader
        title="线索管理"
        description="外部获客入口：查重 → 创建 → 分配 → 转客户"
        extra={
          <Space wrap>
            <Input
              allowClear
              prefix={<SearchOutlined />}
              placeholder="公司/联系人/邮箱"
              style={{ width: 200 }}
              onPressEnter={(e) => {
                setPage(1);
                setKeyword((e.target as HTMLInputElement).value);
              }}
            />
            <Select
              allowClear
              placeholder="状态"
              style={{ width: 110 }}
              value={status}
              onChange={(v) => {
                setPage(1);
                setStatus(v);
              }}
              options={[
                { value: 'NEW', label: '新建' },
                { value: 'ASSIGNED', label: '已分配' },
                { value: 'CONVERTED', label: '已转化' },
                { value: 'INVALID', label: '无效' },
              ]}
            />
            <Select
              allowClear
              placeholder="线索等级"
              style={{ width: 130 }}
              value={leadLevel}
              onChange={(v) => {
                setPage(1);
                setLeadLevel(v);
              }}
              options={LEAD_LEVEL_OPTIONS}
            />
            <Select
              allowClear
              placeholder="渠道分类"
              style={{ width: 120 }}
              value={channel}
              onChange={(v) => {
                setPage(1);
                setChannel(v);
              }}
              options={LEAD_CHANNEL_OPTIONS}
            />
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              placeholder="负责人"
              style={{ width: 140 }}
              value={ownerId}
              onChange={(v) => {
                setPage(1);
                setOwnerId(v);
              }}
              options={(users ?? []).map((u) => ({ value: u.id, label: u.name }))}
            />
            <Space size={4}>
              <Switch
                checked={overdue}
                onChange={(v) => {
                  setPage(1);
                  setOverdue(v);
                }}
              />
              <Typography.Text>仅看逾期</Typography.Text>
            </Space>
            <Button icon={<ReloadOutlined />} onClick={() => refetch()} />
            <HasPermission permission="lead:create">
              <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
                新建线索
              </Button>
            </HasPermission>
          </Space>
        }
      />

      <Table<Lead>
        rowKey="id"
        size="small"
        loading={isFetching}
        columns={columns}
        dataSource={data?.items ?? []}
        scroll={{ x: 1500 }}
        pagination={{
          current: data?.page ?? 1,
          pageSize: data?.page_size ?? 10,
          total: data?.total ?? 0,
          onChange: setPage,
        }}
      />

      <Modal
        title="新建线索"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={createMutation.isPending}
        width={640}
        destroyOnClose
      >
        <Form form={form} layout="vertical" requiredMark={false} onFinish={(v) => void startCreate(v)}>
          <Form.Item name="name" label="公司名称" rules={[{ required: true }]}>
            <Input placeholder="客户公司名称" />
          </Form.Item>
          <Form.Item name="contact_name" label="联系人">
            <Input />
          </Form.Item>
          <Form.Item name="email" label="邮箱">
            <Input />
          </Form.Item>
          <Form.Item name="phone" label="电话">
            <Input />
          </Form.Item>
          <Form.Item name="country" label="国家">
            <Input />
          </Form.Item>
          <Form.Item name="lead_level" label="线索等级" initialValue="B">
            <Select options={LEAD_LEVEL_OPTIONS} />
          </Form.Item>
          <Form.Item name="channel" label="客户渠道分类" initialValue="OTHER">
            <Select options={LEAD_CHANNEL_OPTIONS} />
          </Form.Item>
          <Form.Item
            name="source"
            label="来源"
            initialValue="EXHIBITION"
            tooltip="原「来源」字段，与渠道分类并存"
          >
            <Select
              options={[
                { value: 'EXHIBITION', label: '展会' },
                { value: 'YUNQUTONG', label: '云渠通' },
                { value: 'WEBSITE', label: '官网' },
                { value: 'DIRECT', label: '主动开发' },
                { value: 'B2B', label: 'B2B平台' },
                { value: 'REFERRAL', label: '客户推荐' },
                { value: 'AGENT', label: '代理商' },
                { value: 'SOCIAL', label: '社媒' },
                { value: 'OTHER', label: '其他' },
              ]}
            />
          </Form.Item>
          <Form.Item name="requirement_text" label="具体需求内容">
            <Input.TextArea rows={3} maxLength={5000} showCount />
          </Form.Item>
          <Form.Item name="background" label="初步背景调查">
            <Input.TextArea rows={3} maxLength={5000} showCount />
          </Form.Item>
          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="发现疑似重复"
        open={!!dedup}
        onCancel={() => setDedup(null)}
        onOk={confirmDedupCreate}
        okText="仍然创建"
        cancelText="返回修改"
        confirmLoading={createMutation.isPending}
        width={820}
      >
        {dedup?.result.definite.length ? (
          <Alert
            type="error"
            showIcon
            message="存在确定重复记录"
            description="名称/邮箱/电话与已有记录一致。请先打开已有记录确认；确属新线索时填写查重说明后仍然创建。"
            style={{ marginBottom: 12 }}
          />
        ) : (
          <Alert
            type="warning"
            showIcon
            message="存在疑似重复记录"
            description="邮箱域名或名称（忽略法律后缀）相似，请确认后再创建。"
            style={{ marginBottom: 12 }}
          />
        )}
        <Table
          rowKey={(row) => `${row.kind}-${row.id}`}
          size="small"
          pagination={false}
          columns={candidateColumns}
          dataSource={dedup?.result.candidates ?? []}
          scroll={{ y: 260 }}
          style={{ marginBottom: 12 }}
        />
        <Input.TextArea
          rows={2}
          maxLength={200}
          showCount
          placeholder={dedup?.result.definite.length ? '查重说明（必填）' : '查重说明（可选）'}
          value={dedupNote}
          onChange={(e) => setDedupNote(e.target.value)}
        />
      </Modal>

      <Drawer
        title={`分配线索 ${assignTarget?.lead_no ?? ''}`}
        open={!!assignTarget}
        onClose={() => setAssignTarget(null)}
        width={420}
      >
        <Typography.Paragraph type="secondary">{assignTarget?.name}</Typography.Paragraph>
        <Form
          form={assignForm}
          layout="vertical"
          onFinish={(v) => assignTarget && assignMutation.mutate({ id: assignTarget.id, owner: v.owner_id })}
        >
          <Form.Item name="owner_id" label="负责人" rules={[{ required: true, message: '请选择负责人' }]}>
            <Select
              placeholder="选择业务员"
              options={(users ?? []).map((u) => ({
                value: u.id,
                label: `${u.name}（${u.department_name ?? '未分配部门'}）`,
              }))}
            />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={assignMutation.isPending} block>
            确认分配
          </Button>
        </Form>
      </Drawer>

      <Modal
        title={`转客户 ${convertTarget?.lead_no ?? ''}`}
        open={!!convertTarget}
        onCancel={() => {
          setConvertTarget(null);
          setConvertCandidates(null);
        }}
        onOk={() => convertForm.submit()}
        confirmLoading={convertMutation.isPending}
        width={680}
        destroyOnClose
      >
        <Typography.Paragraph type="secondary">{convertTarget?.name}</Typography.Paragraph>
        {convertCandidates ? (
          <>
            <Alert
              type={convertCandidates.definite.length ? 'error' : 'warning'}
              showIcon
              message={
                convertCandidates.definite.length
                  ? '已存在同名客户，只能关联既有客户'
                  : '存在疑似重复客户，请选择关联或说明非重复后新建'
              }
              style={{ marginBottom: 12 }}
            />
            <Table
              rowKey={(row) => `${row.kind}-${row.id}`}
              size="small"
              pagination={false}
              columns={candidateColumns}
              dataSource={convertCandidates.candidates}
              scroll={{ y: 200 }}
              style={{ marginBottom: 12 }}
            />
          </>
        ) : null}
        <Form form={convertForm} layout="vertical" onFinish={submitConvert}>
          <Form.Item name="mode" label="处理方式" rules={[{ required: true }]}>
            <Radio.Group
              options={[
                { value: 'link', label: '关联既有客户' },
                ...(convertCandidates?.definite.length ? [] : [{ value: 'create', label: '新建客户' }]),
              ]}
            />
          </Form.Item>
          <Form.Item
            noStyle
            shouldUpdate={(prev, next) => prev.mode !== next.mode}
          >
            {({ getFieldValue }) =>
              getFieldValue('mode') === 'link' ? (
                <Form.Item name="link_company_id" label="关联客户" rules={[{ required: true }]}>
                  <Select
                    showSearch
                    optionFilterProp="label"
                    placeholder="选择既有客户"
                    options={(convertCandidates?.candidates ?? [])
                      .filter((c) => c.company_id)
                      .map((c) => ({
                        value: c.company_id as string,
                        label: `${c.company_name ?? c.name}（${c.ref}）`,
                      }))}
                  />
                </Form.Item>
              ) : (
                <Form.Item
                  name="non_duplicate_reason"
                  label="非重复说明"
                  rules={[{ required: !!convertCandidates, message: '请填写非重复说明' }]}
                >
                  <Input.TextArea rows={2} maxLength={200} showCount />
                </Form.Item>
              )
            }
          </Form.Item>
          <Form.Item name="relation_type" label="联系人关系类型" initialValue="OTHER">
            <Select options={CONTACT_RELATION_OPTIONS} />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
