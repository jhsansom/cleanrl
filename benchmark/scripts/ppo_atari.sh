
for seed in {1..2}
do
    (sleep 0.3 && nohup xvfb-run -a python ppo_atari_visual.py \
    --gym-id BeamRiderNoFrameskip-v4 \
    --total-timesteps 10000000 \
    --wandb-project-name cleanrl.benchmark \
    --wandb-entity cleanrl \
    --prod-mode \
    --cuda \
    --capture-video \
    --seed $seed
    ) >& /dev/null &
done

for seed in {1..2}
do
    (sleep 0.3 && nohup xvfb-run -a python ppo_atari_visual.py \
    --gym-id QbertNoFrameskip-v4 \
    --total-timesteps 10000000 \
    --wandb-project-name cleanrl.benchmark \
    --wandb-entity cleanrl \
    --prod-mode \
    --cuda \
    --capture-video \
    --seed $seed
    ) >& /dev/null &
done

for seed in {1..2}
do
    (sleep 0.3 && nohup xvfb-run -a python ppo_atari_visual.py \
    --gym-id SpaceInvadersNoFrameskip-v4 \
    --total-timesteps 10000000 \
    --wandb-project-name cleanrl.benchmark \
    --wandb-entity cleanrl \
    --prod-mode \
    --cuda \
    --capture-video \
    --seed $seed
    ) >& /dev/null &
done

for seed in {1..2}
do
    (sleep 0.3 && nohup xvfb-run -a python ppo_atari_visual.py \
    --gym-id PongNoFrameskip-v4 \
    --total-timesteps 10000000 \
    --wandb-project-name cleanrl.benchmark \
    --wandb-entity cleanrl \
    --prod-mode \
    --cuda \
    --capture-video \
    --seed $seed
    ) >& /dev/null &
done

for seed in {1..2}
do
    (sleep 0.3 && nohup xvfb-run -a python ppo_atari_visual.py \
    --gym-id BreakoutNoFrameskip-v4 \
    --total-timesteps 10000000 \
    --wandb-project-name cleanrl.benchmark \
    --wandb-entity cleanrl \
    --prod-mode \
    --cuda \
    --capture-video \
    --seed $seed
    ) >& /dev/null &
done
