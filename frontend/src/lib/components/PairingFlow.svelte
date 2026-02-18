<script lang="ts">
	import type { DeviceInfo } from '../types';

	export let device: DeviceInfo | null = null;
	export let protocol: string = '';
	export let onPinSubmit: (pin: string) => void = () => {};
	export let onCancel: () => void = () => {};

	let pin: string = '';
	let error: string = '';

	function handleSubmit() {
		if (pin.length === 0) {
			error = 'Введите PIN';
			return;
		}
		onPinSubmit(pin);
		pin = '';
		error = '';
	}
</script>

{#if device}
	<div class="pairing-flow p-4 bg-white rounded border">
		<h3 class="font-semibold mb-2">Сопряжение с {device.name}</h3>
		<p class="text-sm text-gray-600 mb-4">
			Введите PIN, отображаемый на экране Apple TV
		</p>
		<div class="space-y-3">
			<div>
				<label class="block text-sm font-medium mb-1">PIN</label>
				<input
					type="text"
					bind:value={pin}
					class="w-full border rounded px-3 py-2"
					placeholder="0000"
					maxlength="4"
					on:keydown={(e) => {
						if (e.key === 'Enter') {
							handleSubmit();
						}
					}}
				/>
				{#if error}
					<p class="text-red-500 text-xs mt-1">{error}</p>
				{/if}
			</div>
			<div class="flex gap-2">
				<button
					class="flex-1 bg-blue-500 text-white px-4 py-2 rounded hover:bg-blue-600"
					on:click={handleSubmit}
				>
					Подтвердить
				</button>
				<button
					class="flex-1 bg-gray-300 text-gray-700 px-4 py-2 rounded hover:bg-gray-400"
					on:click={onCancel}
				>
					Отмена
				</button>
			</div>
		</div>
	</div>
{/if}
