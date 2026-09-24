'use client';

import { ArrowLeftOutlined, PlusOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  App,
  Button,
  Card,
  Col,
  Descriptions,
  Empty,
  Form,
  Input,
  List,
  Modal,
  Row,
  Select,
  Space,
  Steps,
  Table,
  Tag,
  Timeline,
  Typography,
} from 'antd';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useMemo, useState } from 'react';

import HasPermission from '@/components/HasPermission';
import PageHeader from '@/components/common/PageHeader';
import StatusTag from '@/components/common/StatusTag';
import { api, buildQuery } from '@/lib/api';
import { formatDateTime, formatMoney } from '@/lib/format';
import type { PageResult } from '@/types';
import type { ActivityItem, Opportunity, StageCatalog, TaskItem } from '@/types/business';

const STAGE_ORDER = [
  'NEW',
  'QUALIFIED',
  'REQUIREMENT',
  'INQUIRY',
  'PRICING',
  'QUOTATION',
  'SAMPLE',
  'NEGOTIATION',
  'WON',
];

export default function OpportunityDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id as string;
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [stageOpen, setStageOpen] = useState(false);
  const [activityOpen, setActivityOpen] = useState(false);
  const [taskOpen, setTaskOpen] = useState(false);
  const [stageForm] = Form.useForm();
  const [activityForm] = Form.useForm();
  const [taskForm] = Form.useForm();

  const opp = useQuery({
    queryKey: ['opportunity', id],
    queryFn: () => api.get<Opportunity>(`/opportunities/${id}`),
    enabled: !!id,
  });

  const catalog = useQuery({
    queryKey: ['stage-catalog'],
    queryFn: () => api.get<StageCatalog[]>('/opportunities/stages'),
  });

  const activities = useQuery({
    queryKey: ['activities', id],
    queryFn: () =>
      api.get<PageResult<ActivityItem>>(`/activities${buildQuery({ opportunity_id: id, page_size: 50 })}`),
    enabled: !!id,
  });

  const tasks = useQuery({
    queryKey: ['tasks', id],
    queryFn: () =>
      api.get<PageResult<TaskItem>>(`/tasks${buildQuery({ biz_id: id, page_size: 50 })}`),
    enabled: !!id,
  });

  const inquiries = useQuery({
    queryKey: ['opp-inquiries', id],
    queryFn: () =>
      api.get<PageResult<{ id: string; inquiry_no: string; status: string; currency: string; created_at: string }>>(
        `/inquiries${buildQuery({ opportunity_id: id, page_size: 50 })}`,
      ),
    enabled: !!id,
  });

  const currentRule = useMemo(
    () => catalog.data?.find((c) => c.value === opp.data?.stage),
    [catalog.data, opp.data?.stage],
  );

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['opportunity', id] });
    queryClient.invalidateQueries({ queryKey: ['activities', id] });
    queryClient.invalidateQueries({ queryKey: ['tasks', id] });
    queryClient.invalidateQueries({ queryKey: ['opportunities-kanban'] });
  };

  const stageMutation = useMutation({
    mutationFn: (values: Record<string, unknown>) =>
      api.patch(`/opportunities/${id}/stage`, { ...values, stage: values.stage }),
    onSuccess: () => {
      message.success('阶段已更新');
      setStageOpen(false);
      stageForm.resetFields();
      invalidate();
    },
    onError: (e: Error) => message.error(e.message),
  });

  const activityMutation = useMutation({
    mutationFn: (values: Record<string, unknown>) =>
      api.post('/activities', { ...values, biz_type: 'OPPORTUNITY', biz_id: id, opportunity_id: id, company_id: opp.data?.company_id }),
    onSuccess: () => {
      message.success('跟进记录已保存');
      setActivityOpen(false);
      activityForm.resetFields();
      invalidate();
    },
    onError: (e: Error) => message.error(e.message),
  });

  const taskMutation = useMutation({
    mutationFn: (values: Record<string, unknown>) =>
      api.post('/tasks', { ...values, biz_type: 'OPPORTUNITY', biz_id: id }),
    onSuccess: () => {
      message.success('任务已创建');
      setTaskOpen(false);
      taskForm.resetFields();
      invalidate();
    },
    onError: (e: Error) => message.error(e.message),
  });

  const completeTask = useMutation({
    mutationFn: (taskId: string) => api.post(`/tasks/${taskId}/complete`),
    onSuccess: () => {
      message.success('任务已完成');
      queryClient.invalidateQueries({ queryKey: ['tasks', id] });
    },
  });

  if (!opp.data) {
    return <Empty description={opp.isFetching ? '加载中...' : '商机不存在'} />;
  }

  const data = opp.data;
  const stepIndex = STAGE_ORDER.indexOf(data.stage);

  return (
    <>
      <PageHeader
        title={`${data.name}（${data.opportunity_no}）`}
        description={data.company_name ?? undefined}
        extra={
          <Space>
            <Link href="/opportunities">
              <Button icon={<ArrowLeftOutlined />}>返回看板</Button>
            </Link>
            <HasPermission permission="opportunity:stage">
              <Button
                type="primary"
                onClick={() => {
                  setStageOpen(true);
                  stageForm.setFieldsValue({ stage: currentRule?.next_stages?.[0] });
                }}
              >
                阶段流转
              </Button>
            </HasPermission>
          </Space>
        }
      />

      <Card size="small" style={{ marginBottom: 16 }}>
        <Steps
          size="small"
          current={stepIndex < 0 ? 0 : stepIndex}
          status={data.stage === 'LOST' ? 'error' : undefined}
          items={STAGE_ORDER.map((s) => ({
            title: catalog.data?.find((c) => c.value === s)?.label ?? s,
          }))}
        />
        {data.stage === 'LOST' ? (
          <Typography.Text type="danger" style={{ display: 'block', marginTop: 12 }}>
            流失原因：{data.lost_reason ?? '-'}
          </Typography.Text>
        ) : null}
      </Card>

      <Row gutter={16}>
        <Col xs={24} lg={14}>
          <Card title="商机信息" size="small">
            <Descriptions bordered size="small" column={2}>
              <Descriptions.Item label="阶段">
                <StatusTag value={data.stage} />
              </Descriptions.Item>
              <Descriptions.Item label="状态">
                <StatusTag value={data.status} />
              </Descriptions.Item>
              <Descriptions.Item label="预计金额">
                {formatMoney(data.estimated_amount, data.currency)}
              </Descriptions.Item>
              <Descriptions.Item label="赢单金额">
                {formatMoney(data.won_amount, data.currency)}
              </Descriptions.Item>
              <Descriptions.Item label="产品类别">{data.product_category ?? '-'}</Descriptions.Item>
              <Descriptions.Item label="数量">{data.quantity ?? '-'}</Descriptions.Item>
              <Descriptions.Item label="预估成交日">{data.expected_close_date ?? '-'}</Descriptions.Item>
              <Descriptions.Item label="成交概率">
                {data.probability ? `${data.probability}%` : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="竞争对手">{data.competitor ?? '-'}</Descriptions.Item>
              <Descriptions.Item label="报价金额">
                {formatMoney(data.quotation_amount, data.currency)}
              </Descriptions.Item>
              <Descriptions.Item label="需求描述" span={2}>
                {data.requirement ?? '-'}
              </Descriptions.Item>
              <Descriptions.Item label="下一步动作" span={2}>
                {data.next_action ?? '-'}
              </Descriptions.Item>
            </Descriptions>
          </Card>

          <Card
            title="询价单"
            size="small"
            style={{ marginTop: 16 }}
            extra={<Link href="/inquiries">全部</Link>}
          >
            <Table
              rowKey="id"
              size="small"
              pagination={false}
              dataSource={inquiries.data?.items ?? []}
              columns={[
                {
                  title: '询价单号',
                  dataIndex: 'inquiry_no',
                  render: (v: string, row) => <Link href={`/inquiries/${row.id}`}>{v}</Link>,
                },
                {
                  title: '状态',
                  dataIndex: 'status',
                  width: 110,
                  render: (v: string) => <StatusTag value={v} />,
                },
                { title: '币种', dataIndex: 'currency', width: 80 },
              ]}
            />
          </Card>
        </Col>

        <Col xs={24} lg={10}>
          <Card
            title="跟进记录"
            size="small"
            extra={
              <HasPermission permission="opportunity:update">
                <Button size="small" icon={<PlusOutlined />} onClick={() => setActivityOpen(true)}>
                  记录
                </Button>
              </HasPermission>
            }
          >
            {(activities.data?.items ?? []).length === 0 ? (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无跟进" />
            ) : (
              <Timeline
                items={(activities.data?.items ?? []).map((a) => ({
                  color: 'blue',
                  children: (
                    <div>
                      <Space size={6}>
                        <Tag>{a.type}</Tag>
                        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                          {formatDateTime(a.happened_at ?? a.created_at)}
                        </Typography.Text>
                      </Space>
                      <div style={{ marginTop: 4 }}>{a.content}</div>
                    </div>
                  ),
                }))}
              />
            )}
          </Card>

          <Card
            title="任务"
            size="small"
            style={{ marginTop: 16 }}
            extra={
              <HasPermission permission="task:create">
                <Button size="small" icon={<PlusOutlined />} onClick={() => setTaskOpen(true)}>
                  新建
                </Button>
              </HasPermission>
            }
          >
            <List
              size="small"
              dataSource={tasks.data?.items ?? []}
              locale={{ emptyText: '暂无任务' }}
              renderItem={(t) => (
                <List.Item
                  actions={[
                    t.status === 'PENDING' ? (
                      <a key="done" onClick={() => completeTask.mutate(t.id)}>
                        完成
                      </a>
                    ) : (
                      <StatusTag key="st" value={t.status} />
                    ),
                  ]}
                >
                  <List.Item.Meta
                    title={t.title}
                    description={
                      <Space size={6}>
                        <StatusTag value={t.priority} />
                        <span>{t.due_date ? formatDateTime(t.due_date) : '无截止时间'}</span>
                      </Space>
                    }
                  />
                </List.Item>
              )}
            />
          </Card>
        </Col>
      </Row>

      <Modal
        title="商机阶段流转"
        open={stageOpen}
        onCancel={() => setStageOpen(false)}
        onOk={() => stageForm.submit()}
        confirmLoading={stageMutation.isPending}
        destroyOnClose
      >
        <Typography.Paragraph type="secondary">
          当前阶段：{currentRule?.label ?? data.stage}
          {currentRule?.next_stages?.length
            ? `，可流转至：${currentRule.next_stages.join(' / ')}`
            : '（终态，不可再流转）'}
        </Typography.Paragraph>
        <Form form={stageForm} layout="vertical" onFinish={(v) => stageMutation.mutate(v)}>
          <Form.Item name="stage" label="目标阶段" rules={[{ required: true }]}>
            <Select
              options={(currentRule?.next_stages ?? []).map((s) => ({
                value: s,
                label: catalog.data?.find((c) => c.value === s)?.label ?? s,
              }))}
            />
          </Form.Item>
          <Form.Item
            noStyle
            shouldUpdate={(prev, cur) => prev.stage !== cur.stage}
          >
            {({ getFieldValue }) => {
              const stage = getFieldValue('stage');
              if (stage === 'LOST') {
                return (
                  <Form.Item name="lost_reason" label="流失原因" rules={[{ required: true }]}>
                    <Input.TextArea rows={2} placeholder="必填" />
                  </Form.Item>
                );
              }
              if (stage === 'WON') {
                return (
                  <Form.Item name="won_amount" label="成交金额" rules={[{ required: true }]}>
                    <Input />
                  </Form.Item>
                );
              }
              if (stage === 'QUALIFIED') {
                return (
                  <>
                    <Form.Item name="requirement" label="需求描述" rules={[{ required: true }]}>
                      <Input.TextArea rows={2} />
                    </Form.Item>
                    <Form.Item name="estimated_amount" label="预计金额" rules={[{ required: true }]}>
                      <Input />
                    </Form.Item>
                  </>
                );
              }
              if (stage === 'REQUIREMENT') {
                return (
                  <>
                    <Form.Item name="product_category" label="产品类别" rules={[{ required: true }]}>
                      <Input />
                    </Form.Item>
                    <Form.Item name="quantity" label="数量" rules={[{ required: true }]}>
                      <Input />
                    </Form.Item>
                  </>
                );
              }
              if (stage === 'SAMPLE') {
                return (
                  <Form.Item name="sample_record" label="样品记录" rules={[{ required: true }]}>
                    <Input.TextArea rows={2} />
                  </Form.Item>
                );
              }
              if (stage === 'NEGOTIATION') {
                return (
                  <Form.Item name="negotiation_record" label="谈判记录" rules={[{ required: true }]}>
                    <Input.TextArea rows={2} />
                  </Form.Item>
                );
              }
              return null;
            }}
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="新增跟进记录"
        open={activityOpen}
        onCancel={() => setActivityOpen(false)}
        onOk={() => activityForm.submit()}
        confirmLoading={activityMutation.isPending}
        destroyOnClose
      >
        <Form form={activityForm} layout="vertical" onFinish={(v) => activityMutation.mutate(v)}>
          <Form.Item name="type" label="类型" initialValue="NOTE">
            <Select
              options={[
                { value: 'CALL', label: '电话' },
                { value: 'EMAIL', label: '邮件' },
                { value: 'MEETING', label: '会议' },
                { value: 'VISIT', label: '拜访' },
                { value: 'NOTE', label: '备注' },
              ]}
            />
          </Form.Item>
          <Form.Item name="content" label="内容" rules={[{ required: true }]}>
            <Input.TextArea rows={4} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="新建任务"
        open={taskOpen}
        onCancel={() => setTaskOpen(false)}
        onOk={() => taskForm.submit()}
        confirmLoading={taskMutation.isPending}
        destroyOnClose
      >
        <Form form={taskForm} layout="vertical" onFinish={(v) => taskMutation.mutate(v)}>
          <Form.Item name="title" label="任务标题" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="content" label="说明">
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item name="priority" label="优先级" initialValue="MEDIUM">
            <Select
              options={[
                { value: 'HIGH', label: '高' },
                { value: 'MEDIUM', label: '中' },
                { value: 'LOW', label: '低' },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
