import { defineConfig } from 'astro/config'
import starlight from '@astrojs/starlight'

export default defineConfig({
  integrations: [
    starlight({
      title: '秒部 API 文档',
      defaultLocale: 'root',
      locales: {
        root: { label: '简体中文', lang: 'zh-CN' },
      },
      social: [
        { icon: 'github', label: 'GitHub', href: 'https://github.com/wizardleeen/miaobu' },
      ],
      sidebar: [
        {
          label: '快速开始',
          items: [
            { label: '简介', slug: 'getting-started' },
            { label: '身份认证', slug: 'getting-started/authentication' },
          ],
        },
        {
          label: 'API 参考',
          items: [
            { label: '概述', slug: 'api-reference' },
            { label: '项目', slug: 'api-reference/projects' },
            { label: '部署', slug: 'api-reference/deployments' },
            { label: '域名', slug: 'api-reference/domains' },
            { label: '环境变量', slug: 'api-reference/environment-variables' },
          ],
        },
        {
          label: '概念',
          items: [
            { label: '部署生命周期', slug: 'concepts/deploy-lifecycle' },
            { label: '项目类型', slug: 'concepts/project-types' },
          ],
        },
      ],
    }),
  ],
})
