import nest
import matplotlib.pyplot as plt

nest.ResetKernel()
neuron_exc = nest.Create('iaf_psc_alpha')  
neuron_target = nest.Create('iaf_psc_alpha') 
dc_gen = nest.Create('dc_generator', params={'amplitude': 500.0})
nest.Connect(dc_gen, neuron_exc)
nest.Connect(neuron_exc, neuron_target, syn_spec={'weight': 1000.0})
voltmeter_exc = nest.Create('multimeter', params={'interval': 0.1, 'record_from': ['V_m']})
voltmeter_target = nest.Create('multimeter', params={'interval': 0.1, 'record_from': ['V_m']})
nest.Connect(voltmeter_exc, neuron_exc)
nest.Connect(voltmeter_target, neuron_target)
spike_detector = nest.Create('spike_recorder')
nest.Connect(neuron_exc, spike_detector)
nest.Connect(neuron_target, spike_detector)

plt.ion()
fig, ax = plt.subplots(3, 1, figsize=(10, 12))
ax[0].set_title('Membrane Potential of Excitatory Neuron')
ax[0].set_xlabel('Time (ms)')
ax[0].set_ylabel('Membrane Potential (mV)')
ax[0].set_ylim(-80, 20)
ax[0].set_xlim(0, 500)
ax[0].grid()
ax[1].set_title('Membrane Potential of Target Neuron')
ax[1].set_xlabel('Time (ms)')
ax[1].set_ylabel('Membrane Potential (mV)')
ax[1].set_ylim(-80, 20)
ax[1].set_xlim(0, 500)
ax[1].grid()
ax[2].set_title('Spikes from Both Neurons')
ax[2].set_xlabel('Time (ms)')
ax[2].set_ylabel('Neuron ID')
ax[2].set_ylim(0.5, 2.5)  
ax[2].set_xlim(0, 500)
ax[2].grid()
for t in range(0, 500, 10):  
    nest.Simulate(10) 
    vm_exc = nest.GetStatus(voltmeter_exc)[0]['events']
    vm_target = nest.GetStatus(voltmeter_target)[0]['events']
    spikes = nest.GetStatus(spike_detector)[0]['events']
    ax[0].plot(vm_exc['times'], vm_exc['V_m'], color='blue')
    ax[1].plot(vm_target['times'], vm_target['V_m'], color='orange')
    if spikes:
        ax[2].vlines(spikes['times'], spikes['senders'], spikes['senders'] + 0.5, color='red')
    plt.draw()
    plt.pause(0.001) 
plt.ioff() 
plt.show()
