module.exports = {
  apps: [
    {
      name: 'rain-sensor',
      script: 'rain_sensor/__main__.py',
      args: '--config config.yaml run',
      interpreter: 'python3',
      cwd: '/home/pi/rainsensor',
      env: { PYTHONPATH: '/home/pi/rainsensor' },
      restart_delay: 5000,
      max_restarts: 10,
      autorestart: true,
    },
    {
      name: 'rain-sensor-web',
      script: 'rain_sensor/__main__.py',
      args: '--config config.yaml web',
      interpreter: 'python3',
      cwd: '/home/pi/rainsensor',
      env: { PYTHONPATH: '/home/pi/rainsensor' },
      restart_delay: 5000,
      max_restarts: 10,
      autorestart: true,
    },
  ],
};
