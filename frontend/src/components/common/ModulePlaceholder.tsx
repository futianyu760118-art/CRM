'use client';

import { Card, Empty, Space, Tag, Typography } from 'antd';
import type { ReactNode } from 'react';

interface ModulePlaceholderProps {
  title: string;
  module: string;
  milestone: string;
  permission?: string;
  description?: string;
  children?: ReactNode;
}

/** 业务模块占位页：M1 仅搭框架，功能在对应里程碑交付。 */
export function ModulePlaceholder({
  title,
  module,
  milestone,
  permission,
  description,
  children,
}: ModulePlaceholderProps) {
  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Space size={8} wrap>
        <Typography.Title level={4} style={{ margin: 0 }}>
          {title}
        </Typography.Title>
        <Tag color="processing">{milestone}</Tag>
        <Tag>{module}</Tag>
        {permission ? <Tag color="gold">{permission}</Tag> : null}
      </Space>
      {description ? <Typography.Text type="secondary">{description}</Typography.Text> : null}
      <Card>
        {children ?? (
          <Empty description={`该模块将在 ${milestone} 交付，M1 阶段仅完成系统骨架与权限接入`} />
        )}
      </Card>
    </Space>
  );
}

export default ModulePlaceholder;
