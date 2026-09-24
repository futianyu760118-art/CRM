'use client';

import { ArrowLeftOutlined, ReloadOutlined } from '@ant-design/icons';
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
  Modal,
  Row,
  Space,
  Statistic,
  Steps,
  Tag,
  Typography,
} from 'antd';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useState } from 'react';

import HasPermission from '@/components/HasPermission';
import PageHeader from '@/components/common/PageHeader';
import StatusTag from '@/components/common/StatusTag';
import { api } from '@/lib/api';
import { formatDateTime, formatNumber, formatPercent } from '@/lib/format';
import type { Pricing } from '@/types/business';

const COST_LABELS: Record<string, string> = {
  material_cost: '材料成本',
  labor_cost: '人工成本',
  packaging_cost: '包装成本',
  freight_cost: '运费',
  tooling_cost: '模具费',
  customization_cost: '定制费',
  moq_cost: '起订量成本',
  other_cost: '其他成本',
};

export default function PricingDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id as string;
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [approveOpen, setApproveOpen] = useState(false);
  const [approved, setApproved] = useState(true);
  const [form] = Form.useForm();

  const query = useQuery({
    queryKey: ['pricing', id],
    queryFn: () => api.get<Pricing>(`/pricing/${id}`),
    enabled: !!id,
  });

  const doAction = useMutation({
    mutationFn: async ({ action, comment }: { action: 'submit' | 'approve'; comment?: string }) => {
      if (action === 'submit') return api.post(`/pricing/${id}/submit`);
      return api.post(
        `/pricing/${id}/approve${comment ? `?comment=${encodeURIComponent(comment)}` : ''}`,
        { approved, comment },
      );
    },
    onSuccess: () => {
      message.success('操作成功');
      setApproveOpen(false);
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ['pricing', id] });
      queryClient.invalidateQueries({ queryKey: ['pricing-list'] });
      queryClient.invalidateQueries({ queryKey: ['approvals'] });
    },
    onError: (e: Error) => message.error(e.message),
  });

  if (!query.data) {
    return <Empty description={query.isFetching ? '加载中...' : '核价记录不存在'} />;
  }

  const data = query.data;
  const statusStep =
    data.status === 'DRAFT' ? 0 : data.status === 'PENDING_APPROVAL' ? 1 : data.status === 'APPROVED' ? 2 : 0;

  return (
    <>
      <PageHeader
        title={`核价记录 V${data.version}`}
        description={`询价单 ${data.inquiry_no ?? '-'} · ${data.company_name ?? ''}`}
        extra={
          <Space>
            <Link href="/pricing">
              <Button icon={<ArrowLeftOutlined />}>返回列表</Button>
            </Link>
            <Button icon={<ReloadOutlined />} onClick={() => query.refetch()} />
            <HasPermission permission="pricing:submit">
              <Button
                type="primary"
                disabled={data.status !== 'DRAFT'}
                loading={doAction.isPending}
                onClick={() => doAction.mutate({ action: 'submit' })}
              >
                提交审批
              </Button>
            </HasPermission>
            <HasPermission permission="pricing:approve">
              <Button
                disabled={data.status !== 'PENDING_APPROVAL'}
                onClick={() => {
                  setApproved(true);
                  setApproveOpen(true);
                }}
              >
                审批
              </Button>
            </HasPermission>
          </Space>
        }
      />

      <Card size="small" style={{ marginBottom: 16 }}>
        <Steps
          size="small"
          current={statusStep}
          status={data.status === 'REJECTED' ? 'error' : undefined}
          items={[
            { title: '草稿' },
            { title: '待审批' },
            { title: data.status === 'REJECTED' ? '已驳回' : '已通过' },
          ]}
        />
      </Card>

      <Row gutter={16}>
        <Col xs={24} lg={10}>
          <Card title="核价结果" size="small">
            <Row gutter={16}>
              <Col span={12}>
                <Statistic
                  title="总成本"
                  value={data.total_cost ?? 0}
                  precision={2}
                  prefix="$"
                />
              </Col>
              <Col span={12}>
                <Statistic
                  title="底价（单位成本）"
                  value={data.floor_price ?? 0}
                  precision={4}
                  prefix="$"
                />
              </Col>
              <Col span={12} style={{ marginTop: 16 }}>
                <Statistic
                  title="建议售价"
                  value={data.suggested_price ?? 0}
                  precision={4}
                  prefix="$"
                />
              </Col>
              <Col span={12} style={{ marginTop: 16 }}>
                <Statistic title="目标利润率" value={formatPercent(data.target_margin)} />
              </Col>
            </Row>
            {data.can_view_cost === false ? (
              <Tag color="red" style={{ marginTop: 12 }}>
                当前角色无成本字段查看权限
              </Tag>
            ) : null}
            {data.can_view_floor === false ? (
              <Tag color="orange" style={{ marginTop: 12 }}>
                当前角色无底价查看权限
              </Tag>
            ) : null}
          </Card>

          <Card title="单据信息" size="small" style={{ marginTop: 16 }}>
            <Descriptions bordered size="small" column={1}>
              <Descriptions.Item label="状态">
                <StatusTag value={data.status} />
              </Descriptions.Item>
              <Descriptions.Item label="币种">{data.currency}</Descriptions.Item>
              <Descriptions.Item label="审批时间">
                {formatDateTime(data.approved_at)}
              </Descriptions.Item>
              <Descriptions.Item label="创建时间">
                {formatDateTime(data.created_at)}
              </Descriptions.Item>
              <Descriptions.Item label="备注">
                <Typography.Text style={{ whiteSpace: 'pre-wrap' }}>{data.remark ?? '-'}</Typography.Text>
              </Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>

        <Col xs={24} lg={14}>
          <Card title="成本明细" size="small">
            <Descriptions bordered size="small" column={2}>
              {Object.entries(COST_LABELS).map(([key, label]) => {
                const value = (data as unknown as Record<string, number | null>)[key];
                return (
                  <Descriptions.Item key={key} label={label}>
                    {value === null || value === undefined ? (
                      <Tag color="red">无权限</Tag>
                    ) : (
                      formatNumber(value, 2)
                    )}
                  </Descriptions.Item>
                );
              })}
              <Descriptions.Item label="合计总成本" span={2}>
                <b>{data.total_cost === null ? <Tag color="red">无权限</Tag> : formatNumber(data.total_cost, 2)}</b>
              </Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>
      </Row>

      <Modal
        title="核价审批"
        open={approveOpen}
        onCancel={() => setApproveOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={doAction.isPending}
        destroyOnClose
        footer={[
          <Button key="cancel" onClick={() => setApproveOpen(false)}>
            取消
          </Button>,
          <Button
            key="reject"
            danger
            onClick={() => {
              setApproved(false);
              form.submit();
            }}
          >
            驳回
          </Button>,
          <Button
            key="ok"
            type="primary"
            onClick={() => {
              setApproved(true);
              form.submit();
            }}
          >
            通过
          </Button>,
        ]}
      >
        <Form form={form} layout="vertical" onFinish={(v) => doAction.mutate({ action: 'approve', comment: v.comment })}>
          <Form.Item name="comment" label="审批意见">
            <Input.TextArea rows={3} placeholder="可选" />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
