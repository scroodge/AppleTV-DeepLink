<script lang="ts">
	import type { DeviceInfo, PairedDevice } from '../types';

	export let devices: DeviceInfo[] = [];
	export let pairedDevices: PairedDevice[] = [];
	export let defaultDeviceId: string | null = null;
	export let onPair: (device: DeviceInfo, protocol: string) => void = () => {};
	export let onSetDefault: (deviceId: string) => void = () => {};
	export let onDelete: ((deviceId: string) => void) | undefined = undefined;
	export let onUpdate: ((deviceId: string, data: { name?: string; address?: string }) => void) | undefined = undefined;

	let editingDeviceId: string | null = null;
	let editName = '';
	let editAddress = '';

	function isPaired(deviceId: string): boolean {
		const device = pairedDevices.find((d) => d.device_id === deviceId);
		return device ? (device.is_paired === true) : false;
	}

	function getPairedProtocols(deviceId: string): string[] {
		const device = pairedDevices.find((d) => d.device_id === deviceId);
		return device?.paired_protocols ?? [];
	}

	function isAdded(deviceId: string): boolean {
		return pairedDevices.some((d) => d.device_id === deviceId);
	}

	function getProtocols(device: DeviceInfo): string[] {
		return device.protocols || [];
	}

	function isProtocolPaired(deviceId: string, protocol: string): boolean {
		return getPairedProtocols(deviceId).includes(protocol.toLowerCase());
	}

	function allProtocolsPaired(device: DeviceInfo): boolean {
		const protocols = getProtocols(device);
		const paired = getPairedProtocols(device.device_id);
		return protocols.length > 0 && protocols.every((p) => paired.includes(p.toLowerCase()));
	}

	function startEdit(device: DeviceInfo) {
		editingDeviceId = device.device_id;
		editName = device.name;
		editAddress = device.address;
	}

	function cancelEdit() {
		editingDeviceId = null;
	}

	function submitEdit() {
		if (!editingDeviceId || !onUpdate) return;
		onUpdate(editingDeviceId, { name: editName.trim() || undefined, address: editAddress.trim() || undefined });
		editingDeviceId = null;
	}
</script>

<div class="device-list space-y-2">
	{#if devices.length === 0}
		<p class="text-gray-500 text-sm">Устройства не найдены</p>
	{:else}
		{#each devices as device (device.device_id)}
			<div class="device-item border rounded p-3 bg-white">
				<div class="flex justify-between items-start">
					<div class="flex-1">
						{#if editingDeviceId === device.device_id && onUpdate}
							<div class="space-y-2">
								<div>
									<label class="block text-xs text-gray-500">Название</label>
									<input
										type="text"
										bind:value={editName}
										class="w-full border rounded px-2 py-1 text-sm"
										placeholder="Apple TV"
									/>
								</div>
								<div>
									<label class="block text-xs text-gray-500">IP-адрес</label>
									<input
										type="text"
										bind:value={editAddress}
										class="w-full border rounded px-2 py-1 text-sm"
										placeholder="192.168.1.100"
									/>
								</div>
								<div class="flex gap-2">
									<button
										class="text-xs px-2 py-1 bg-green-500 text-white rounded hover:bg-green-600"
										on:click={submitEdit}
									>
										Сохранить
									</button>
									<button
										class="text-xs px-2 py-1 bg-gray-300 rounded hover:bg-gray-400"
										on:click={cancelEdit}
									>
										Отмена
									</button>
								</div>
							</div>
						{:else}
							<h3 class="font-semibold">{device.name}</h3>
							<p class="text-sm text-gray-600">{device.address}</p>
							{#if device.device_type === 'legacy'}
								<p class="text-xs text-orange-600 mt-1">
									⚠ Apple TV 1st generation - ограниченная поддержка
								</p>
							{/if}
							<div class="mt-1">
								{#if getProtocols(device).length > 0}
									{#each getProtocols(device) as protocol}
										<span class="inline-block bg-gray-200 text-xs px-2 py-1 rounded mr-1">
											{protocol}
										</span>
									{/each}
								{:else}
									<span class="text-xs text-gray-500">Протоколы не поддерживаются</span>
								{/if}
							</div>
						{/if}
					</div>
					<div class="flex flex-col gap-2 items-end">
						{#if getProtocols(device).length > 0}
							<div class="flex flex-wrap gap-2 items-center justify-end">
								{#each getProtocols(device) as protocol}
									<span class="text-xs text-gray-600">{protocol}:</span>
									{#if isProtocolPaired(device.device_id, protocol)}
										<span class="text-green-600 text-xs">✓ Сопряжён</span>
									{:else}
										<button
											class="text-xs px-2 py-1 bg-green-500 text-white rounded hover:bg-green-600"
											on:click={() => onPair(device, protocol)}
										>
											Сопряжение
										</button>
									{/if}
								{/each}
							</div>
							{#if allProtocolsPaired(device)}
								<span class="text-green-600 text-sm">✓ Все протоколы сопряжены</span>
							{/if}
						{:else}
							<span class="text-xs text-gray-500">Протоколы не обнаружены</span>
						{/if}
						{#if isAdded(device.device_id)}
							{#if defaultDeviceId === device.device_id}
								<span class="text-blue-600 text-sm">(По умолчанию)</span>
							{:else}
								<button
									class="text-xs px-2 py-1 bg-blue-500 text-white rounded hover:bg-blue-600"
									on:click={() => onSetDefault(device.device_id)}
								>
									Установить по умолчанию
								</button>
							{/if}
						{/if}
					</div>
				</div>
				{#if isAdded(device.device_id) && (onDelete || onUpdate) && editingDeviceId !== device.device_id}
					<div class="mt-2 pt-2 border-t border-gray-100 flex gap-2">
						{#if onUpdate}
							<button
								class="text-xs px-2 py-1 text-gray-600 border border-gray-300 rounded hover:bg-gray-100"
								on:click={() => startEdit(device)}
							>
								Изменить
							</button>
						{/if}
						{#if onDelete}
							<button
								class="text-xs px-2 py-1 text-red-600 border border-red-300 rounded hover:bg-red-50"
								on:click={() => onDelete(device.device_id)}
							>
								Удалить
							</button>
						{/if}
					</div>
				{/if}
			</div>
		{/each}
	{/if}
</div>
