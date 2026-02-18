<script lang="ts">
	import { onMount } from 'svelte';
	import { browser } from '$app/environment';
	import type { ToastMessage } from '../types';

	export let toast: ToastMessage;

	let mounted = false;
	let visible = false;

	onMount(() => {
		if (!browser) return;
		mounted = true;
		setTimeout(() => (visible = true), 10);
		
		const duration = toast.duration || 3000;
		setTimeout(() => {
			visible = false;
			setTimeout(() => {
				// Trigger remove event
				const event = new CustomEvent('toast:remove', { detail: toast.id });
				window.dispatchEvent(event);
			}, 300);
		}, duration);
	});

	function getColorClass() {
		switch (toast.type) {
			case 'success':
				return 'bg-green-500';
			case 'error':
				return 'bg-red-500';
			case 'info':
				return 'bg-blue-500';
			default:
				return 'bg-gray-500';
		}
	}
</script>

{#if mounted}
	<div
		class="toast {getColorClass()} text-white px-4 py-2 rounded shadow-lg mb-2 transition-all duration-300 {visible ? 'opacity-100 translate-y-0' : 'opacity-0 -translate-y-2'}"
		role="alert"
	>
		{toast.message}
	</div>
{/if}

<style>
	.toast {
		min-width: 200px;
		max-width: 400px;
	}
</style>
