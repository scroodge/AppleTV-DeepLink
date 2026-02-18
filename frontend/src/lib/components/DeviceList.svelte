<script lang="ts">
	import type { DeviceInfo, PairedDevice } from '../types';

	export let devices: DeviceInfo[] = [];
	export let pairedDevices: PairedDevice[] = [];
	export let defaultDeviceId: string | null = null;
	export let onPair: (device: DeviceInfo, protocol: string) => void = () => {};
	export let onSetDefault: (deviceId: string) => void = () => {};
	export let onDelete: ((deviceId: string) => void) | undefined = undefined;
	export let onUpdate: ((deviceId: string, data: { name?: string; address?: string }) => void) | undefined = undefined;

	// Track selected protocol for each device
	let selectedProtocols: Record<string, string> = {};
	let editingDeviceId: string | null = null;
	let editName = '';
	let editAddress = '';

	function isPaired(deviceId: string): boolean {
		const device = pairedDevices.find((d) => d.device_id === deviceId);
		// Device is considered paired only if it exists AND has actual credentials
		return device ? (device.is_paired === true) : false;
	}
	
	function isAdded(deviceId: string): boolean {
		// Check if device exists in database (even without credentials)
		return pairedDevices.some((d) => d.device_id === deviceId);
	}

	function getProtocols(device: DeviceInfo): string[] {
		return device.protocols || [];
	}

	function getSelectedProtocol(deviceId: string): string {
		return selectedProtocols[deviceId] || '';
	}

	function setSelectedProtocol(deviceId: string, protocol: string) {
		selectedProtocols[deviceId] = protocol;
	}

	function handlePairClick(device: DeviceInfo) {
		const selected = getSelectedProtocol(device.device_id);
		const protocols = getProtocols(device);
		const protocol = selected || protocols[0];
		if (protocol) {
			onPair(device, protocol);
		}
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
					<div class="flex gap-2 items-center">
						{#if isPaired(device.device_id)}
							<span class="text-green-600 text-sm">✓ Сопряжено</span>
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
						{:else if isAdded(device.device_id)}
							<div class="flex flex-col gap-2 items-end">
								<span class="text-orange-600 text-sm">⚠ Требуется сопряжение</span>
								{#if getProtocols(device).length > 0}
									<div class="flex gap-2 items-center">
										<select
											class="text-xs border rounded px-2 py-1"
											value={getSelectedProtocol(device.device_id)}
											on:change={(e) => {
												setSelectedProtocol(device.device_id, e.currentTarget.value);
											}}
										>
											<option value="">Выбрать протокол</option>
											{#each getProtocols(device) as protocol}
												<option value={protocol}>{protocol}</option>
											{/each}
										</select>
										<button
											class="text-xs px-3 py-1 bg-green-500 text-white rounded hover:bg-green-600 disabled:bg-gray-400 disabled:cursor-not-allowed"
											on:click={() => handlePairClick(device)}
											disabled={getProtocols(device).length === 0}
										>
											Сопряжение
										</button>
									</div>
								{:else}
									<span class="text-xs text-gray-500">Протоколы не обнаружены</span>
								{/if}
							</div>
						{:else}
							{#if getProtocols(device).length > 0}
								<div class="flex gap-2 items-center">
									<select
										class="text-xs border rounded px-2 py-1"
										value={getSelectedProtocol(device.device_id)}
										on:change={(e) => {
											setSelectedProtocol(device.device_id, e.currentTarget.value);
										}}
									>
										<option value="">Выбрать протокол</option>
										{#each getProtocols(device) as protocol}
											<option value={protocol}>{protocol}</option>
										{/each}
									</select>
									<button
										class="text-xs px-3 py-1 bg-green-500 text-white rounded hover:bg-green-600 disabled:bg-gray-400 disabled:cursor-not-allowed"
										on:click={() => handlePairClick(device)}
										disabled={getProtocols(device).length === 0}
									>
										Сопряжение
									</button>
								</div>
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
