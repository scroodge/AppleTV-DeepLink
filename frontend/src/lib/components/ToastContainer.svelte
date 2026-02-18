<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { browser } from '$app/environment';
	import Toast from './Toast.svelte';
	import type { ToastMessage } from '../types';

	let toasts: ToastMessage[] = [];

	function addToast(message: string, type: 'success' | 'error' | 'info' = 'info', duration?: number) {
		const toast: ToastMessage = {
			id: Date.now().toString() + Math.random().toString(36).substr(2, 9),
			message,
			type,
			duration,
		};
		toasts = [...toasts, toast];
	}

	function removeToast(id: string) {
		toasts = toasts.filter((t) => t.id !== id);
	}

	function handleToastEvent(event: CustomEvent) {
		removeToast(event.detail);
	}

	function handleShowToast(event: CustomEvent) {
		const { message, type, duration } = event.detail;
		addToast(message, type, duration);
	}

	onMount(() => {
		if (!browser) return;
		window.addEventListener('toast:remove', handleToastEvent as EventListener);
		window.addEventListener('toast:show', handleShowToast as EventListener);
	});

	onDestroy(() => {
		if (!browser) return;
		window.removeEventListener('toast:remove', handleToastEvent as EventListener);
		window.removeEventListener('toast:show', handleShowToast as EventListener);
	});
</script>

<div class="toast-container fixed top-4 right-4 z-50">
	{#each toasts as toast (toast.id)}
		<Toast {toast} />
	{/each}
</div>
