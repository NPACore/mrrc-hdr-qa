#!/usr/bin/env bash
set -euo pipefail

# rerun in readline wrapper for a nicer prompt if not already and is avaiable
if [[ -z "${IN_RLWRAP:-}" && -n "$(command -v rlwrap)" ]]; then
   export IN_RLWRAP=1
   echo "# relaunching with rlwrap"
   rlwrap -pgreen -S "> " $0
   exit $?
fi

port=${PORT:-9090}
kill_mrqart() { pgrep -f "python.*mrqart.*$port" |xargs -r kill; }

# re/start makeshift mrqart daemon created with tmux
# is run at start of this script and anytime a restart is request
# (kill with first user signal user )
# NB. tornado will restart itself when mrqart.py is edited
#     this will clear STATE but not reset the inotify or websocks part of the code (?)
#     sigusr1 restart might not be necessary (but still is a cool trick)
start_mrqart() {
  echo "# re/starting python server in tmux"
  kill_mrqart
  sleep .2 # wait for tmux to exit
  LOGLEVEL=DEBUG tmux new -s mrqart -d ./mrqart.py -p $port --watch sim/
}
trap start_mrqart SIGUSR1

# setup sim directory
mkdir -p sim/
rm -r sim/* || :

# launch mrqart in tmux in the background
! tmux ls | grep -q mrqrt &&
   start_mrqart ||
   echo "# already running mrqart!?"


# if we are not using SSH, we can launch the browser
if [ -z "${SSH_CLIENT:-}" ]; then
  # wait for server to come online
  sleep .5
  xdg-open http://127.0.0.1:$port
  xterm -e 'tmux attach -t mrqart' >/dev/null 2>&1 &
else
  cat <<HEREDOC
1. connect to remote ports with ssh port forwarding like
  ssh -L 5000:localhost:5000 -L $port:localhost:$port remot'
2. launch local browser
  http://127.0.0.1:$port
3. see running server in tmux
  ssh -t remote -- tmux a -t mrqart
HEREDOC

fi

sim_cp(){
   cp $1 sim/$(basename $1).$(date +%s).dcm
   echo "# $_"
}
options_msg="'rew', 'B0', 'bad', 'restart', or 'quit'"
echo "Input $options_msg"
while read -p "send: " choice; do
   case $choice in
      rew*) sim_cp example_dicoms/RewardedAnti_good.dcm ;;
      B*) sim_cp example_dicoms/B1Map_newline.dcm ;;
      bad) sim_cp example_dicoms/RewardedAnti_wrongTR.dcm ;;
      # send sigusr1 to this process. trap will catch and trigger py restart
      restart) kill -s SIGUSR1 $$; echo "# restart via pid $$!";;
      q*) echo "goodbye"; kill_mrqart; break;;
      *) echo "Unknown option '$choice'. must be $options_msg";;
   esac
done

