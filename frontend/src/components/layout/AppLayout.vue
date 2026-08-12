<template>
  <a-layout class="app-layout">
    <!-- 侧边栏 -->
    <sidebar-component />

    <!-- 右侧内容区 -->
    <a-layout class="main-area">
      <!-- 顶部栏 -->
      <topbar-component />
      <!-- 页面内容 -->
      <a-layout-content class="content-area">
        <router-view v-slot="{ Component }">
          <transition name="fade-slide" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </a-layout-content>
    </a-layout>
  </a-layout>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useAppStore } from '@/stores/app'
import SidebarComponent from './Sidebar.vue'
import TopbarComponent from './Topbar.vue'

const appStore = useAppStore()

onMounted(() => {
  appStore.initTheme()
})
</script>

<style scoped>
.app-layout {
  height: 100vh;
  overflow: hidden;
}

.main-area {
  margin-left: v-bind("appStore.sidebarCollapsed ? 'var(--sidebar-collapsed-width)' : 'var(--sidebar-width)'");
  transition: margin-left var(--transition-normal);
  height: 100vh;
  display: flex;
  flex-direction: column;
}

.content-area {
  flex: 1;
  overflow-y: auto;
  background: var(--color-bg-page);
}
</style>
