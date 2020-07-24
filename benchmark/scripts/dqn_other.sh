
for seed in {1..2}
do
    (sleep 0.3 && nohup xvfb-run -a python dqn.py \
    --gym-id CartPole-v1 \
    --total-timesteps 1000000 \
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
    (sleep 0.3 && nohup xvfb-run -a python dqn.py \
    --gym-id Acrobot-v1 \
    --total-timesteps 1000000 \
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
    (sleep 0.3 && nohup xvfb-run -a python dqn.py \
    --gym-id MountainCar-v0 \
    --total-timesteps 1000000 \
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
    (sleep 0.3 && nohup xvfb-run -a python dqn.py \
    --gym-id LunarLander-v2 \
    --total-timesteps 1000000 \
    --wandb-project-name cleanrl.benchmark \
    --wandb-entity cleanrl \
    --prod-mode \
    --cuda \
    --capture-video \
    --seed $seed
    ) >& /dev/null &
done
