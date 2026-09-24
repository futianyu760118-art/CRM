'use client';

import { ReloadOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  App,
  Button,
  Card,
  Descriptions,
  Empty,
  Form,
  Input,
  List,
  Modal,
  Segmented,
  Space,
  Steps,
  Tag,
  Timeline,
  Typography,
} from 'antd';
import Link from 'next/link';
import { useState } from 'react';

import HasPermission from '@/components/HasPermission';
import PageHeader from '@/components/common/PageHeader';
import StatusTag from '@/components/common/StatusTag';
import { api, buildQuery } from '@/lib/api';
import { formatDateTime, formatMoney } from '@/lib/format';
import type { PageResult } from '@/types';
import type { Approval } from '@/types/business';

export default function ApprovalsPage() {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [scope, setScope] = useState<'mine' | 'all'>('mine');
  const [current, setCurrent] = useState<Approval | null>(null);
  const [action, setAction] = useState<'approve' | 'reject'>('approve');
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();

  const query = useQuery({
    queryKey: ['approvals', scope],
    queryFn: () =>
      api.get<PageResult<Approval>>(
        `/approvals${buildQuery({ scope, page_size: 50, ...(scope === 'all' ? { status: 'PENDING' } : {}) })}`,
      ),
  });

  const act = useMutation({
    mutationFn: ({ id, act: a, comment }: { id: string; act: 'approve' | 'reject'; comment?: string }) =>
      api.post(`/approvals/${id}/${a}`, { comment }),
    onSuccess: () => {
      message.success('审批操作成功');
      setOpen(false);
      setCurrent(null);
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ['approvals'] });
      queryClient.invalidateQueries({ queryKey: ['quotations'] });
      queryClient.invalidateQueries({ queryKey: ['pricing-list'] });
      queryClient.invalidateQueries({ queryKey: ['quotation'] });
      queryClient.invalidateQueries({ queryKey: ['pricing'] });
    },
    onError: (e: Error) => message.error(e.message),
  });

  const bizLink = (a: Approval) =>
    a.biz_type === 'QUOTATION' ? `/quotations/${a.biz_id}` : `/pricing/${a.biz_id}`;

  return (
    <>
      <PageHeader
        title="报价审批"
        description="待审批列表 / 审批通过 / 驳回；审批实例 · 任务 · 日志"
        extra={
          <Space>
            <Segmented
              value={scope}
              onChange={(v) => setScope(v as 'mine' | 'all')}
              options={[
                { label: '我的待办', value: 'mine' },
                { label: '全部进行中', value: 'all' },
              ]}
            />
            <Button icon={<ReloadOutlined />} onClick={() => query.refetch()} />
          </Space>
        }
      />

      <List
        loading={query.isFetching}
        dataSource={query.data?.items ?? []}
        locale={{ emptyText: <Empty description="暂无待审批" /> }}
        renderItem={(item) => (
          <Card size="small" style={{ marginBottom: 12 }}>
            <Space direction="vertical" size={8} style={{ width: '100%' }}>
              <Space wrap>
                <Typography.Text strong>{item.title}</Typography.Text>
                <Tag color="blue">{item.biz_type}</Tag>
                <StatusTag value={item.status} />
                <Tag color="gold">
                  第 {item.current_step}/{item.total_steps} 级
                </Tag>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  申请人：{item.applicant_name ?? '-'} · {formatDateTime(item.created_at)}
                </Typography.Text>
              </Space>

              <Descriptions size="small" column={3}>
                <Descriptions.Item label="单据号">
                  <Link href={bizLink(item)}>{item.biz_no ?? item.biz_id}</Link>
                </Descriptions.Item>
                <Descriptions.Item label="金额">
                  {formatMoney(item.amount, item.currency)}
                </Descriptions.Item>
                <Descriptions.Item label="流程">
                  {item.tasks.map((t) => `${t.approver_role ?? '-'}(${t.status})`).join(' → ')}
                </Descriptions.Item>
              </Descriptions>

              <Space>
                <HasPermission permission="approval:approve">
                  <Button
                    type="primary"
                    size="small"
                    disabled={item.status !== 'PENDING'}
                    onClick={() => {
                      setCurrent(item);
                      setAction('approve');
                      setOpen(true);
                    }}
                  >
                    通过
                  </Button>
                </HasPermission>
                <HasPermission permission="approval:reject">
                  <Button
                    size="small"
                    danger
                    disabled={item.status !== 'PENDING'}
                    onClick={() => {
                      setCurrent(item);
                      setAction('reject');
                      setOpen(true);
                    }}
                  >
                    驳回
                  </Button>
                </HasPermission>
              </Space>
            </Space>
          </Card>
        )}
      />

      <Modal
        title={`${action === 'approve' ? '审批通过' : '审批驳回'} - ${current?.title ?? ''}`}
        open={open}
        onCancel={() => setOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={act.isPending}
        destroyOnClose
        width={720}
      >
        {current ? (
          <>
            <Card size="small" style={{ marginBottom: 12 }}>
              <Steps
                size="small"
                current={current.current_step - 1}
                items={current.tasks.map((t) => ({
                  title: `${t.approver_role ?? ''} (${t.step})`,
                  status:
                    t.status === 'APPROVED'
                      ? 'finish'
                      : t.status === 'REJECTED'
                        ? 'error'
                        : t.step === current.current_step
                          ? 'process'
                          : 'wait',
                }))}
              />
              {current.logs?.length ? (
                <Timeline
                  style={{ marginTop: 12 }}
                  items={current.logs.map((l) => ({
                    children: (
                      <span>
                        <Tag>{l.action}</Tag>
                        {l.operator_name ?? '-'} · {formatDateTime(l.created_at)}
                        {l.comment ? ` · ${l.comment}` : ''}
                      </span>
                    ),
                  }))}
                />
              ) : null}
            </Card>
            <Form
              form={form}
              layout="vertical"
              onFinish={(v) => current && act.mutate({ id: current.id, act: action, comment: v.comment })}
            >
              <Form.Item
                name="comment"
                label="审批意见"
                rules={action === 'reject' ? [{ required: true, message: '驳回必须填写原因' }] : []}
              >
                <Input.TextArea rows={3} />
              </Form.Item>
            </Form>
          </>
        ) : null}
      </Modal>
    </>
  );
}
