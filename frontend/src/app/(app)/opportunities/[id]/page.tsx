'use client';

import { ArrowLeftOutlined, PlusOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Descriptions,
  Empty,
  Form,
  Input,
  InputNumber,
  List,
  Modal,
  Radio,
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
import { useState } from 'react';

import HasPermission from '@/components/HasPermission';
import PageHeader from '@/components/common/PageHeader';
import StatusTag from '@/components/common/StatusTag';
import { api, buildQuery } from '@/lib/api';
import { formatDateTime, formatMoney } from '@/lib/format';
import type { PageResult } from '@/types';
import type {
  ActivityItem,
  Opportunity,
  OpportunityTransitions,
  StageCatalog,
  TaskItem,
} from '@/types/business';

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
  const [targetStage, setTargetStage] = useState<string | undefined>();
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

  const transitions = useQuery({
    queryKey: ['opp-transitions', id],
    queryFn: () => api.get<OpportunityTransitions>(`/opportunities/${id}/transitions`),
    enabled: !!id && stageOpen,
  });

  const targets = transitions.data?.targets ?? [];
  const activeStage = targetStage ?? targets[0]?.stage;
  const activeTarget = targets.find((t) => t.stage === activeStage);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['opportunity', id] });
    queryClient.invalidateQueries({ queryKey: ['activities', id] });
    queryClient.invalidateQueries({ queryKey: ['tasks', id] });
    queryClient.invalidateQueries({ queryKey: ['opportunities-kanban'] });
  };

  const stageMutation = useMutation({
    mutationFn: (values: Record<string, unknown>) => api.patch(`/opportunities/${id}/stage`, values),
    onSuccess: () => {
      message.success('阶段已更新');
      setStageOpen(false);
      setTargetStage(undefined);
      stageForm.resetFields();
      queryClient.invalidateQueries({ queryKey: ['opp-transitions', id] });
      invalidate();
    },
    onError: (e: Error) => message.error(e.message),
  });

  const submitStage = async () => {
    if (!activeStage || !activeTarget) return;
    const values = (await stageForm.validateFields().catch(() => null)) as Record<string, unknown> | null;
    if (!values) return;
    const payload: Record<string, unknown> = { stage: activeStage };
    activeTarget.required.forEach((item) => {
      if (values[item.field] !== undefined && values[item.field] !== null) {
        payload[item.field] = values[item.field];
      }
    });
    stageMutation.mutate(payload);
  };

  const renderFieldInput = (field: string, label: string) => {
    switch (field) {
      case 'requirement':
      case 'sample_record':
      case 'negotiation_record':
      case 'lost_reason':
        return <Input.TextArea rows={2} placeholder={`请填写${label}`} />;
      case 'estimated_amount':
      case 'won_amount':
      case 'quotation_amount':
        return <InputNumber min={0.01} precision={2} style={{ width: '100%' }} placeholder={`请填写${label}`} />;
      case 'quantity':
        return <InputNumber min={1} precision={0} style={{ width: '100%' }} placeholder={`请填写${label}`} />;
      default:
        return <Input placeholder={`请填写${label}`} />;
    }
  };

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
                  setTargetStage(undefined);
                  stageForm.resetFields();
                  setStageOpen(true);
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
        onOk={submitStage}
        confirmLoading={stageMutation.isPending}
        okButtonProps={{ disabled: !activeTarget }}
        destroyOnClose
        width={640}
      >
        <Typography.Paragraph type="secondary">
          当前阶段：{transitions.data?.current_label ?? data.stage}
          。系统已按目标阶段校验必填信息，并自动从来源单据带出可满足项。
        </Typography.Paragraph>
        {transitions.isFetching ? <Empty description="加载中..." /> : null}
        {!transitions.isFetching && targets.length === 0 ? (
          <Alert type="info" showIcon message="当前为终态，不可再流转" />
        ) : null}
        {targets.length > 0 ? (
          <>
            <Radio.Group
              value={activeStage}
              onChange={(e) => {
                setTargetStage(e.target.value as string);
                stageForm.resetFields();
              }}
              style={{ marginBottom: 12 }}
            >
              <Space wrap>
                {targets.map((t) => (
                  <Radio.Button key={t.stage} value={t.stage}>
                    {t.label}
                    {t.satisfied ? '（信息齐全）' : ''}
                  </Radio.Button>
                ))}
              </Space>
            </Radio.Group>
            {activeTarget ? (
              <>
                {!activeTarget.role_allowed ? (
                  <Alert
                    type="warning"
                    showIcon
                    style={{ marginBottom: 12 }}
                    message={`该阶段仅限【${activeTarget.roles.join('、')}】操作，可请主管代办`}
                  />
                ) : null}
                <Typography.Text strong>必填信息预检</Typography.Text>
                <div style={{ margin: '8px 0 12px' }}>
                  <Space wrap>
                    {activeTarget.required.length === 0 ? <Tag color="green">无必填项</Tag> : null}
                    {activeTarget.required.map((r) => (
                      <Tag key={r.field} color={r.satisfied ? 'green' : 'red'}>
                        {r.label}：{r.satisfied ? '已满足' : '待填写'}
                        {r.source ? `（${r.source}）` : ''}
                      </Tag>
                    ))}
                  </Space>
                </div>
                <Form form={stageForm} layout="vertical" preserve={false}>
                  {activeTarget.required
                    .filter((r) => !r.satisfied)
                    .map((r) =>
                      r.field === 'inquiry_id' || r.field === 'pricing_id' ? (
                        <Alert
                          key={r.field}
                          type="warning"
                          showIcon
                          style={{ marginBottom: 12 }}
                          message={`${r.label}：未找到可自动带出的来源单据，请先完成对应询价/核价后再流转`}
                        />
                      ) : (
                        <Form.Item
                          key={r.field}
                          name={r.field}
                          label={r.label}
                          rules={[{ required: true, message: `请填写${r.label}` }]}
                        >
                          {renderFieldInput(r.field, r.label)}
                        </Form.Item>
                      ),
                    )}
                </Form>
              </>
            ) : null}
          </>
        ) : null}
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
