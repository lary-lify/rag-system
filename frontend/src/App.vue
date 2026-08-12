<template>
  <ConfigProvider :theme="antTheme">
    <router-view />
  </ConfigProvider>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ConfigProvider } from 'ant-design-vue'
import { useAppStore } from '@/stores/app'

const appStore = useAppStore()

/** Ant Design 主题算法 (浅色/深色) */
const antTheme = computed(() => {
  return appStore.theme === 'dark'
    ? { algorithm: undefined } // 深色依赖 CSS 变量控制
    : {}
})
</script>

<style>
#app {
  height: 100vh;
  overflow: hidden;
}
</style>
